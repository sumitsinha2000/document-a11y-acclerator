import { useState, useEffect } from "react"

const features = [
  {
    title: "Automated PDF Scanning",
    description: "Instantly scan PDFs for accessibility issues with our advanced detection engine",
    icon: (
      <svg className="w-12 h-12" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
        />
      </svg>
    ),
    image: "/automated-pdf-scanning-accessibility-detection.jpg",
  },
  {
    title: "Intelligent Auto-Fix",
    description: "AI-powered automatic remediation of common accessibility issues",
    icon: (
      <svg className="w-12 h-12" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
      </svg>
    ),
    image: "/ai-powered-automatic-fix-accessibility.jpg",
  },
  {
    title: "Batch Processing",
    description: "Process multiple documents simultaneously with group management",
    icon: (
      <svg className="w-12 h-12" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"
        />
      </svg>
    ),
    image: "/batch-processing-multiple-documents-management.jpg",
  },
  {
    title: "Comprehensive Reports",
    description: "Detailed accessibility reports with actionable insights and compliance scores",
    icon: (
      <svg className="w-12 h-12" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
        />
      </svg>
    ),
    image: "/accessibility-reports-compliance-scores-analytics.jpg",
  },
]

export default function LoadingScreen({ onComplete }) {
  const [currentFeature, setCurrentFeature] = useState(0)
  const [progress, setProgress] = useState(0)
  const [isComplete, setIsComplete] = useState(false)

  const featureDuration = 2500 // 2.5 seconds per feature
  const totalDuration = features.length * featureDuration

  useEffect(() => {
    // Progress animation
    const progressInterval = setInterval(() => {
      setProgress((prev) => {
        const newProgress = prev + (100 / totalDuration) * 50
        if (newProgress >= 100) {
          clearInterval(progressInterval)
          setIsComplete(true)
          setTimeout(() => {
            onComplete()
          }, 500)
          return 100
        }
        return newProgress
      })
    }, 50)

    // Feature slideshow
    const featureInterval = setInterval(() => {
      setCurrentFeature((prev) => {
        if (prev >= features.length - 1) {
          clearInterval(featureInterval)
          return prev
        }
        return prev + 1
      })
    }, featureDuration)

    return () => {
      clearInterval(progressInterval)
      clearInterval(featureInterval)
    }
  }, [onComplete])

  return (
    <div className="fixed inset-0 w-full h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50 overflow-hidden">
      <div className="flex h-full">
        {/* Left Side - Content */}
        <div className="w-full lg:w-1/2 flex flex-col justify-center px-8 md:px-16 lg:px-24 py-12">
          {/* Logo and Title */}
          <div className="mb-12">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-12 h-12 bg-indigo-600 rounded-xl flex items-center justify-center">
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  className="w-7 h-7 text-white"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth={2}
                >
                  <path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z" />
                  <path d="M14 2v4a2 2 0 0 0 2 2h4" />
                </svg>
              </div>
              <h1 className="text-3xl font-bold text-gray-900">Document A11y Accelerator</h1>
            </div>
            <p className="text-lg text-gray-600">Making PDFs accessible for everyone</p>
          </div>

          {/* Features List with Progress */}
          <div className="space-y-6 mb-12">
            {features.map((feature, index) => (
              <div
                key={index}
                className={`transition-all duration-500 ${
                  index === currentFeature
                    ? "opacity-100 scale-100"
                    : index < currentFeature
                      ? "opacity-40 scale-95"
                      : "opacity-30 scale-95"
                }`}
              >
                <div className="flex items-start gap-4">
                  {/* Icon */}
                  <div
                    className={`flex-shrink-0 w-16 h-16 rounded-2xl flex items-center justify-center transition-all duration-500 ${
                      index === currentFeature
                        ? "bg-indigo-600 text-white shadow-lg shadow-indigo-200"
                        : index < currentFeature
                          ? "bg-indigo-100 text-indigo-600"
                          : "bg-gray-100 text-gray-400"
                    }`}
                  >
                    {feature.icon}
                  </div>

                  {/* Content */}
                  <div className="flex-1 min-w-0">
                    <h3
                      className={`text-xl font-semibold mb-2 transition-colors duration-500 ${
                        index === currentFeature ? "text-gray-900" : "text-gray-500"
                      }`}
                    >
                      {feature.title}
                    </h3>
                    <p
                      className={`text-sm leading-relaxed transition-colors duration-500 ${
                        index === currentFeature ? "text-gray-600" : "text-gray-400"
                      }`}
                    >
                      {feature.description}
                    </p>

                    {/* Individual Progress Bar */}
                    {index === currentFeature && (
                      <div className="mt-3 h-1 bg-gray-200 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-indigo-600 rounded-full transition-all"
                          style={{
                            animation: `slideProgress ${featureDuration}ms linear forwards`,
                          }}
                        />
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Overall Progress */}
          <div className="space-y-3">
            <div className="flex items-center justify-between text-sm">
              <span className="text-gray-600 font-medium">
                {isComplete ? "Ready to start!" : `Loading ${currentFeature + 1} of ${features.length}`}
              </span>
              <span className="text-indigo-600 font-bold">{Math.round(progress)}%</span>
            </div>
            <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-indigo-600 to-purple-600 rounded-full transition-all duration-100"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>
        </div>

        {/* Right Side - Images */}
        <div className="hidden lg:flex w-1/2 items-center justify-center p-12 bg-gradient-to-br from-indigo-100 to-purple-100">
          <div className="relative w-full h-full max-w-2xl max-h-[600px]">
            {features.map((feature, index) => (
              <div
                key={index}
                className={`absolute inset-0 transition-all duration-700 ${
                  index === currentFeature ? "opacity-100 scale-100 z-10" : "opacity-0 scale-95 z-0"
                }`}
              >
                <div className="w-full h-full bg-white rounded-3xl shadow-2xl overflow-hidden">
                  <img
                    src={feature.image || "/placeholder.svg"}
                    alt={feature.title}
                    className="w-full h-full object-cover"
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* CSS Animation Keyframes */}
      <style>{`
        @keyframes slideProgress {
          from {
            width: 0%;
          }
          to {
            width: 100%;
          }
        }
      `}</style>
    </div>
  )
}
