/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Do NOT set output: "standalone" — that is for Docker/Node hosts.
  // Netlify's @netlify/plugin-nextjs needs the default Next build output.
};

export default nextConfig;
