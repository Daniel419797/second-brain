const nextConfig = {
  reactStrictMode: true,
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  experimental: {
    turbopackFileSystemCacheForDev: false
  }
};

export default nextConfig;
