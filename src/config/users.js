const crypto = require('node:crypto');

const PASSWORD_PEPPER =
  process.env.AUTH_PASSWORD_PEPPER || 'huerto-connect-dev-password-pepper-change-in-production';

const VALID_ROLES = ['admin', 'manager', 'user'];
const DEFAULT_ROLE = 'user';

const demoUsers = [
  {
    id: 'usr-admin-01',
    nombre: 'Administrador',
    apellidos: 'Huerto',
    email: 'admin@huertoconnect.com',
    password: 'Admin12345!',
    role: 'admin'
  },
  {
    id: 'usr-abiel-01',
    nombre: 'Abiel',
    apellidos: '',
    email: 'abielon25@gmail.com',
    password: 'Abiel12345!',
    role: 'admin'
  },
  {
    id: 'usr-productor-01',
    nombre: 'Productor',
    apellidos: 'Demo',
    email: 'productor@huertoconnect.com',
    password: 'Productor123!',
    role: 'user'
  },
  {
    id: 'usr-manager-01',
    nombre: 'Supervisor',
    apellidos: 'Regional',
    email: 'manager@huertoconnect.com',
    password: 'Manager123!',
    role: 'manager'
  }
];

function generateSalt(email) {
  return crypto
    .createHash('sha256')
    .update(`${email.toLowerCase()}:huerto-connect`)
    .digest('hex')
    .slice(0, 16);
}

function hashPassword(password, salt) {
  return crypto.scryptSync(`${password}${PASSWORD_PEPPER}`, salt, 64).toString('hex');
}

// Mutable user store
const usersByEmail = new Map();

function seedDemoUsers() {
  for (const user of demoUsers) {
    const normalizedEmail = user.email.toLowerCase();
    const passwordSalt = generateSalt(normalizedEmail);

    usersByEmail.set(normalizedEmail, {
      id: user.id,
      nombre: user.nombre,
      apellidos: user.apellidos,
      name: [user.nombre, user.apellidos].filter(Boolean).join(' '),
      email: normalizedEmail,
      passwordSalt,
      passwordHash: hashPassword(user.password, passwordSalt),
      role: user.role || DEFAULT_ROLE,
      google_id: null,
      profile_picture: null,
      estado: 'Activo',
      emailVerificado: true,
      created_at: new Date().toISOString()
    });
  }
}

seedDemoUsers();

function findUserByEmail(email) {
  if (typeof email !== 'string') {
    return null;
  }

  return usersByEmail.get(email.toLowerCase()) ?? null;
}

function emailExists(email) {
  if (typeof email !== 'string') {
    return false;
  }

  return usersByEmail.has(email.toLowerCase());
}

function addUser({ nombre, apellidos, email, passwordHash, passwordSalt }) {
  const normalizedEmail = email.toLowerCase();
  const user = {
    id: `usr-${crypto.randomUUID().slice(0, 8)}`,
    nombre,
    apellidos,
    name: [nombre, apellidos].filter(Boolean).join(' '),
    email: normalizedEmail,
    passwordSalt,
    passwordHash,
    role: DEFAULT_ROLE,
    google_id: null,
    profile_picture: null,
    estado: 'Activo',
    emailVerificado: true,
    created_at: new Date().toISOString()
  };

  usersByEmail.set(normalizedEmail, user);
  return user;
}

function verifyPassword(user, candidatePassword) {
  if (!user || typeof candidatePassword !== 'string') {
    return false;
  }

  const candidateHash = hashPassword(candidatePassword, user.passwordSalt);
  const expected = Buffer.from(user.passwordHash, 'hex');
  const candidate = Buffer.from(candidateHash, 'hex');
  return crypto.timingSafeEqual(expected, candidate);
}

function findUserById(userId) {
  for (const user of usersByEmail.values()) {
    if (user.id === userId) {
      return user;
    }
  }
  return null;
}

function updatePassword(userId, newPasswordHash, newPasswordSalt) {
  const user = findUserById(userId);
  if (!user) {
    return false;
  }

  user.passwordHash = newPasswordHash;
  user.passwordSalt = newPasswordSalt;
  return true;
}

function addOrFindGoogleUser({ email, nombre, apellidos, google_id, profile_picture }) {
  const normalizedEmail = email.toLowerCase();
  const existing = usersByEmail.get(normalizedEmail);
  if (existing) {
    // Update Google profile data on every login
    existing.nombre = nombre || existing.nombre;
    existing.apellidos = apellidos !== undefined ? apellidos : existing.apellidos;
    existing.name = [existing.nombre, existing.apellidos].filter(Boolean).join(' ');
    if (google_id) {
      existing.google_id = google_id;
    }
    existing.profile_picture = profile_picture || null;
    existing.authProvider = existing.authProvider || 'google';
    return existing;
  }

  const user = {
    id: `usr-${crypto.randomUUID().slice(0, 8)}`,
    nombre,
    apellidos: apellidos || '',
    name: [nombre, apellidos].filter(Boolean).join(' '),
    email: normalizedEmail,
    passwordSalt: null,
    passwordHash: null,
    role: DEFAULT_ROLE,
    google_id: google_id || null,
    profile_picture: profile_picture || null,
    authProvider: 'google',
    estado: 'Activo',
    emailVerificado: true,
    created_at: new Date().toISOString()
  };

  usersByEmail.set(normalizedEmail, user);
  return user;
}

function getAllUsers() {
  return Array.from(usersByEmail.values()).map((u) => ({
    id: u.id,
    name: u.name,
    email: u.email,
    role: u.role,
    profile_picture: u.profile_picture,
    estado: u.estado,
    created_at: u.created_at
  }));
}

function updateUserRole(userId, newRole) {
  if (!VALID_ROLES.includes(newRole)) {
    return { success: false, message: 'Rol invalido.' };
  }
  const user = findUserById(userId);
  if (!user) {
    return { success: false, message: 'Usuario no encontrado.' };
  }
  user.role = newRole;
  return { success: true, user };
}

module.exports = {
  addOrFindGoogleUser,
  addUser,
  emailExists,
  findUserById,
  findUserByEmail,
  generateSalt,
  getAllUsers,
  hashPassword,
  updatePassword,
  updateUserRole,
  verifyPassword,
  VALID_ROLES
};
