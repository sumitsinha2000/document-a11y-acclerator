"use client"

import { useState, useEffect } from "react"
import "./LoadingScreen.css"

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
  },
  {
    title: "Intelligent Auto-Fix",
    description: "AI-powered automatic remediation of common accessibility issues",
    icon: (
      <svg className="w-12 h-12" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
      </svg>
    ),
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
    <div className="loading-screen">
      <div className="loading-container">
        {/* Logo and Title */}
        <div className="loading-header">
          <div className="loading-logo">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="logo-icon"
              fill="none"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z" />
              <path d="M14 2v4a2 2 0 0 0 2 2h4" />
            </svg>
          </div>
          <h1 className="loading-title">Document A11y Accelerator</h1>
          <p className="loading-subtitle">Making PDFs accessible for everyone</p>
        </div>

        {/* Features Slideshow */}
        <div className="features-container">
          {features.map((feature, index) => (
            <div
              key={index}
              className={`feature-card ${index === currentFeature ? "active" : ""} ${
                index < currentFeature ? "completed" : ""
              }`}
            >
              <div className="feature-icon">{feature.icon}</div>
              <div className="feature-content">
                <h3 className="feature-title">{feature.title}</h3>
                <p className="feature-description">{feature.description}</p>
              </div>
              {/* Individual progress bar for active feature */}
              {index === currentFeature && (
                <div className="feature-progress-bar">
                  <div
                    className="feature-progress-fill"
                    style={{
                      animation: `fillProgress ${featureDuration}ms linear forwards`,
                    }}
                  />
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Overall Progress Bar */}
        <div className="progress-container">
          <div className="progress-bar">
            <div
              className="progress-fill"
              style={{
                width: `${progress}%`,
                transition: "width 0.05s linear",
              }}
            />
          </div>
          <div className="progress-text">
            <span className="progress-percentage">{Math.round(progress)}%</span>
            <span className="progress-label">
              {isComplete ? "Ready!" : `Loading feature ${currentFeature + 1} of ${features.length}`}
            </span>
          </div>
        </div>

        {/* Loading Dots Animation */}
        {!isComplete && (
          <div className="loading-dots">
            <span className="dot"></span>
            <span className="dot"></span>
            <span className="dot"></span>
          </div>
        )}
      </div>
    </div>
  )
}
