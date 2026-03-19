const crypto = require('node:crypto');

const PASSWORD_PEPPER =
  process.env.AUTH_PASSWORD_PEPPER || 'huerto-connect-dev-password-pepper-change-in-production';

const demoUsers = [
  {
    id: 'usr-admin-01',
    name: 'Administrador Huerto',
    email: 'admin@huertoconnect.com',
    password: 'Admin12345!'
  },
  {
    id: 'usr-abiel-01',
    name: 'Abiel',
    email: 'abielon25@gmail.com',
    password: 'Abiel12345!'
  },
  {
    id: 'usr-productor-01',
    name: 'Productor Demo',
    email: 'productor@huertoconnect.com',
    password: 'Productor123!'
  }
];

function hashPassword(password, salt) {
  return crypto.scryptSync(`${password}${PASSWORD_PEPPER}`, salt, 64).toString('hex');
}

function buildUserIndex() {
  const index = new Map();

  for (const user of demoUsers) {
    const normalizedEmail = user.email.toLowerCase();
    const passwordSalt = crypto
      .createHash('sha256')
      .update(`${normalizedEmail}:huerto-connect`)
      .digest('hex')
      .slice(0, 16);

    index.set(normalizedEmail, {
      id: user.id,
      name: user.name,
      email: normalizedEmail,
      passwordSalt,
      passwordHash: hashPassword(user.password, passwordSalt)
    });
  }

  return index;
}

const usersByEmail = buildUserIndex();

function findUserByEmail(email) {
  if (typeof email !== 'string') {
    return null;
  }

  return usersByEmail.get(email.toLowerCase()) ?? null;
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

module.exports = {
  findUserByEmail,
  verifyPassword
};
