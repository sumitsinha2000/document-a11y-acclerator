/** @type {import('next').NextConfig} */
const nextConfig = {
  eslint: {
    ignoreDuringBuilds: true,
  },
  typescript: {
    ignoreBuildErrors: true,
  },
  images: {
    unoptimized: true,
  },
  async rewrites() {
    // In development, proxy to local servers
    // In production, these won't be used as the frontend will be built and served statically
    if (process.env.NODE_ENV === 'development') {
      return [
        {
          source: '/api/:path*',
          destination: 'http://localhost:5000/api/:path*',
        },
        {
          source: '/:path*',
          destination: 'http://localhost:3000/:path*',
        },
      ]
    }
    return []
  },
}

export default nextConfig
