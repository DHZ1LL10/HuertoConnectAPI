const huertos = [
  {
    id: 'h-01',
    ownerUserId: 'usr-productor-01',
    nombre: 'Huerto Norte',
    region: 'Veracruz',
    municipio: 'Veracruz',
    estado: 'Optimo',
    cultivosActivos: 6,
    salud: 92
  },
  {
    id: 'h-02',
    ownerUserId: 'usr-productor-01',
    nombre: 'Huerto Familiar',
    region: 'Xalapa',
    municipio: 'Xalapa',
    estado: 'Atencion',
    cultivosActivos: 4,
    salud: 74
  },
  {
    id: 'h-03',
    ownerUserId: 'usr-admin-01',
    nombre: 'Invernadero Central',
    region: 'Cordoba',
    municipio: 'Cordoba',
    estado: 'Optimo',
    cultivosActivos: 8,
    salud: 88
  }
];

const alertasPorUsuario = {
  'usr-productor-01': [
    { id: 'a-01', titulo: 'Riesgo de mildiu en tomate', severidad: 'Advertencia', fecha: '2026-03-12 08:30' },
    { id: 'a-02', titulo: 'Pulgon detectado en pimiento', severidad: 'Critico', fecha: '2026-03-11 17:10' }
  ]
};

const recomendacionesPorUsuario = {
  'usr-productor-01': [
    { id: 'r-01', tema: 'Riego', recomendacion: 'Reduce un 15% el riego esta semana por alta humedad.' },
    { id: 'r-02', tema: 'Fertilizacion', recomendacion: 'Prioriza potasio para mejorar floracion.' },
    { id: 'r-03', tema: 'Plagas', recomendacion: 'Aplica control biologico preventivo en zonas de sombra.' }
  ]
};

const historialPorUsuario = {
  'usr-productor-01': [
    { id: 'c-01', cultivo: 'Tomate saladette', huerto: 'Huerto Norte', temporada: '2025 Otono', estado: 'Cosechado' },
    { id: 'c-02', cultivo: 'Lechuga romana', huerto: 'Huerto Familiar', temporada: '2026 Invierno', estado: 'Activo' },
    { id: 'c-03', cultivo: 'Chile serrano', huerto: 'Huerto Norte', temporada: '2026 Primavera', estado: 'En seguimiento' }
  ]
};

const estadisticasPorUsuario = {
  'usr-productor-01': [
    { label: 'Sem 1', value: 42 },
    { label: 'Sem 2', value: 49 },
    { label: 'Sem 3', value: 56 },
    { label: 'Sem 4', value: 63 },
    { label: 'Sem 5', value: 68 }
  ]
};

const defaultDashboardData = {
  alertas: [],
  recomendaciones: [],
  historial: [],
  estadisticas: []
};

function serializeHuerto(huerto) {
  return {
    id: huerto.id,
    nombre: huerto.nombre,
    region: huerto.region,
    municipio: huerto.municipio,
    estado: huerto.estado,
    cultivosActivos: huerto.cultivosActivos,
    salud: huerto.salud
  };
}

function getAllHuertos() {
  return huertos.map(serializeHuerto);
}

function getHuertosByUserId(userId) {
  return huertos.filter((item) => item.ownerUserId === userId).map(serializeHuerto);
}

function getUserDashboard(userId) {
  const userHuertos = getHuertosByUserId(userId);
  return {
    huertos: userHuertos,
    alertas: alertasPorUsuario[userId] ?? defaultDashboardData.alertas,
    recomendaciones: recomendacionesPorUsuario[userId] ?? defaultDashboardData.recomendaciones,
    historial: historialPorUsuario[userId] ?? defaultDashboardData.historial,
    estadisticas: estadisticasPorUsuario[userId] ?? defaultDashboardData.estadisticas
  };
}

module.exports = {
  getAllHuertos,
  getHuertosByUserId,
  getUserDashboard
};
