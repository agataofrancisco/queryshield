import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Só variáveis VITE_* públicas entram no bundle. Nunca ligações à base de dados nem segredos.
export default defineConfig({
  plugins: [react()],
  server: { port: 13200, strictPort: true },
  build: { sourcemap: false },
});
