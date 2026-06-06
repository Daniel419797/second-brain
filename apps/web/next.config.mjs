const nextConfig = {
  reactStrictMode: true,
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  devIndicators: false,
  experimental: {
    turbopackFileSystemCacheForDev: false
  }
};

export default nextConfig;
