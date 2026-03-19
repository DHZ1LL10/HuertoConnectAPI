const app = require('./app');

const API_PORT = Number(process.env.API_PORT || 3000);

app.listen(API_PORT, () => {
  console.log(`Huerto Connect Auth API running on http://localhost:${API_PORT}`);
});
