"use client"

import { useState, useEffect } from "react"
import axios from "axios"
import { FileText, Plus, Trash2, Download, Loader2, CheckCircle2, XCircle } from "lucide-react"

export default function PDFGenerator() {
  const [pdfType, setPdfType] = useState("inaccessible") // "accessible" or "inaccessible"
  const [companyName, setCompanyName] = useState("BrightPath Consulting")
  const [services, setServices] = useState([
    "Strategic Planning",
    "Market Research",
    "Digital Transformation",
    "Change Management",
    "Leadership Coaching",
  ])
  const [newService, setNewService] = useState("")
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState(null)
  const [generatedPdfs, setGeneratedPdfs] = useState([])

  const [accessibilityOptions, setAccessibilityOptions] = useState({
    lowContrast: true,
    missingAltText: true,
    noStructure: true,
    rasterizedText: true,
    improperHeadings: true,
    noLanguage: true,
  })

  useEffect(() => {
    fetchGeneratedPdfs()
  }, [])

  const handleAddService = () => {
    if (newService.trim()) {
      setServices([...services, newService.trim()])
      setNewService("")
    }
  }

  const handleRemoveService = (index) => {
    setServices(services.filter((_, i) => i !== index))
  }

  const handleGenerate = async () => {
    setLoading(true)
    setMessage(null)

    try {
      const response = await axios.post("/api/generate-pdf", {
        companyName,
        services,
        pdfType,
        accessibilityOptions: pdfType === "inaccessible" ? accessibilityOptions : null,
      })

      setMessage({
        type: "success",
        text: `Successfully generated: ${response.data.filename}`,
      })

      setGeneratedPdfs((prev) => {
        const next = [response.data.filename, ...prev.filter((name) => name !== response.data.filename)]
        return next
      })

      await fetchGeneratedPdfs()
    } catch (error) {
      setMessage({
        type: "error",
        text: error.response?.data?.error || "Failed to generate PDF",
      })
    } finally {
      setLoading(false)
    }
  }

  const fetchGeneratedPdfs = async () => {
    try {
      const response = await axios.get("/api/generated-pdfs")
      setGeneratedPdfs(response.data.pdfs || [])
      return response.data.pdfs || []
    } catch (error) {
      console.error("Error fetching generated PDFs:", error)
      return []
    }
  }

  const handleDownload = async (filename) => {
    try {
      const response = await axios.get(`/api/download-generated/${filename}`, {
        responseType: "blob",
      })

      const url = window.URL.createObjectURL(new Blob([response.data]))
      const link = document.createElement("a")
      link.href = url
      link.setAttribute("download", filename)
      document.body.appendChild(link)
      link.click()
      link.remove()
    } catch (error) {
      console.error("Error downloading PDF:", error)
    }
  }

  const toggleOption = (option) => {
    setAccessibilityOptions((prev) => ({
      ...prev,
      [option]: !prev[option],
    }))
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 py-8 px-4">
      <div className="max-w-4xl mx-auto">
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6">
          <div className="flex items-center gap-3 mb-6">
            <FileText className="w-6 h-6 text-blue-600 dark:text-blue-400" />
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white">PDF Generator</h2>
          </div>

          <p className="text-sm text-gray-600 dark:text-gray-400 mb-6">
            Create sample PDFs for testing accessibility features. Choose between accessible or inaccessible PDFs with
            customizable options.
          </p>

          <div className="mb-6">
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">PDF Type</label>
            <div className="grid grid-cols-2 gap-4">
              <button
                onClick={() => setPdfType("accessible")}
                className={`p-4 rounded-lg border-2 transition-all ${
                  pdfType === "accessible"
                    ? "border-green-500 bg-green-50 dark:bg-green-900/20"
                    : "border-gray-200 dark:border-gray-600 hover:border-green-300 dark:hover:border-green-700"
                }`}
              >
                <div className="flex items-center gap-2 mb-2">
                  <CheckCircle2
                    className={`w-5 h-5 ${pdfType === "accessible" ? "text-green-600 dark:text-green-400" : "text-gray-400"}`}
                  />
                  <span
                    className={`font-medium ${pdfType === "accessible" ? "text-green-900 dark:text-green-300" : "text-gray-700 dark:text-gray-300"}`}
                  >
                    Accessible PDF
                  </span>
                </div>
                <p className="text-xs text-gray-600 dark:text-gray-400">
                  Follows WCAG guidelines with proper structure, contrast, and metadata
                </p>
              </button>

              <button
                onClick={() => setPdfType("inaccessible")}
                className={`p-4 rounded-lg border-2 transition-all ${
                  pdfType === "inaccessible"
                    ? "border-red-500 bg-red-50 dark:bg-red-900/20"
                    : "border-gray-200 dark:border-gray-600 hover:border-red-300 dark:hover:border-red-700"
                }`}
              >
                <div className="flex items-center gap-2 mb-2">
                  <XCircle
                    className={`w-5 h-5 ${pdfType === "inaccessible" ? "text-red-600 dark:text-red-400" : "text-gray-400"}`}
                  />
                  <span
                    className={`font-medium ${pdfType === "inaccessible" ? "text-red-900 dark:text-red-300" : "text-gray-700 dark:text-gray-300"}`}
                  >
                    Inaccessible PDF
                  </span>
                </div>
                <p className="text-xs text-gray-600 dark:text-gray-400">
                  Contains common accessibility issues for testing purposes
                </p>
              </button>
            </div>
          </div>

          {pdfType === "inaccessible" && (
            <div className="mb-6 p-4 bg-red-50 dark:bg-red-900/10 border border-red-200 dark:border-red-800 rounded-lg">
              <h3 className="text-sm font-medium text-red-900 dark:text-red-300 mb-3">
                Select Accessibility Issues to Include:
              </h3>
              <div className="space-y-2">
                {[
                  { key: "lowContrast", label: "Low Contrast Text", desc: "Light gray text on white background" },
                  { key: "missingAltText", label: "Missing Alt Text", desc: "Images without alternative text" },
                  { key: "noStructure", label: "No Document Structure", desc: "Missing tags and semantic structure" },
                  { key: "rasterizedText", label: "Rasterized Text", desc: "Text as images (not selectable)" },
                  { key: "improperHeadings", label: "Improper Headings", desc: "Incorrect heading hierarchy" },
                  { key: "noLanguage", label: "No Language Declaration", desc: "Missing document language" },
                ].map((option) => (
                  <label
                    key={option.key}
                    className="flex items-start gap-3 p-3 bg-white dark:bg-gray-800 rounded-md cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
                  >
                    <input
                      type="checkbox"
                      checked={accessibilityOptions[option.key]}
                      onChange={() => toggleOption(option.key)}
                      className="mt-1 w-4 h-4 text-red-600 border-gray-300 rounded focus:ring-red-500"
                    />
                    <div className="flex-1">
                      <div className="text-sm font-medium text-gray-900 dark:text-white">{option.label}</div>
                      <div className="text-xs text-gray-600 dark:text-gray-400">{option.desc}</div>
                    </div>
                  </label>
                ))}
              </div>
            </div>
          )}

          <div className="mb-6">
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Company Name</label>
            <input
              type="text"
              value={companyName}
              onChange={(e) => setCompanyName(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm"
              placeholder="Enter company name"
            />
          </div>

          <div className="mb-6">
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Services</label>

            <div className="space-y-2 mb-3">
              {services.map((service, index) => (
                <div key={index} className="flex items-center gap-2">
                  <div className="flex-1 px-3 py-2 bg-gray-50 dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-md text-sm text-gray-900 dark:text-white">
                    {service}
                  </div>
                  <button
                    onClick={() => handleRemoveService(index)}
                    className="p-2 text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-md transition-colors"
                    aria-label={`Remove ${service}`}
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              ))}
            </div>

            <div className="flex gap-2">
              <input
                type="text"
                value={newService}
                onChange={(e) => setNewService(e.target.value)}
                onKeyPress={(e) => e.key === "Enter" && handleAddService()}
                className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm"
                placeholder="Add a service"
              />
              <button
                onClick={handleAddService}
                className="px-4 py-2 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-md hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors flex items-center gap-2 text-sm"
              >
                <Plus className="w-4 h-4" />
                Add
              </button>
            </div>
          </div>

          <button
            onClick={handleGenerate}
            disabled={loading || !companyName.trim()}
            className={`w-full px-4 py-3 rounded-md text-white transition-colors flex items-center justify-center gap-2 font-medium ${
              pdfType === "accessible"
                ? "bg-green-600 hover:bg-green-700 disabled:bg-gray-400"
                : "bg-red-600 hover:bg-red-700 disabled:bg-gray-400"
            } disabled:cursor-not-allowed`}
          >
            {loading ? (
              <>
                <Loader2 className="w-5 h-5 animate-spin" />
                Generating PDF...
              </>
            ) : (
              <>
                <FileText className="w-5 h-5" />
                Generate {pdfType === "accessible" ? "Accessible" : "Inaccessible"} PDF
              </>
            )}
          </button>

          {message && (
            <div
              className={`mt-4 p-4 rounded-md text-sm ${
                message.type === "success"
                  ? "bg-green-50 dark:bg-green-900/20 text-green-800 dark:text-green-300 border border-green-200 dark:border-green-800"
                  : "bg-red-50 dark:bg-red-900/20 text-red-800 dark:text-red-300 border border-red-200 dark:border-red-800"
              }`}
            >
              {message.text}
            </div>
          )}

          {generatedPdfs.length > 0 && (
            <div className="mt-8 pt-6 border-t border-gray-200 dark:border-gray-700">
              <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">Recently Generated PDFs</h3>
              <div className="space-y-2">
                {generatedPdfs.slice(0, 5).map((pdf, index) => (
                  <div
                    key={index}
                    className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-700 rounded-md"
                  >
                    <span className="text-sm text-gray-900 dark:text-white truncate flex-1">{pdf}</span>
                    <button
                      onClick={() => handleDownload(pdf)}
                      className="ml-3 p-2 text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded-md transition-colors"
                      aria-label={`Download ${pdf}`}
                    >
                      <Download className="w-4 h-4" />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {pdfType === "accessible" ? (
          <div className="mt-6 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-4">
            <h3 className="text-sm font-medium text-green-900 dark:text-green-300 mb-2">Accessible PDF Features:</h3>
            <ul className="text-sm text-green-800 dark:text-green-400 space-y-1">
              <li>• High contrast text (WCAG AA compliant)</li>
              <li>• Proper document structure and tagging</li>
              <li>• Alternative text for all images</li>
              <li>• Correct heading hierarchy</li>
              <li>• Language declaration</li>
              <li>• Selectable and searchable text</li>
            </ul>
          </div>
        ) : (
          <div className="mt-6 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
            <h3 className="text-sm font-medium text-red-900 dark:text-red-300 mb-2">Selected Accessibility Issues:</h3>
            <ul className="text-sm text-red-800 dark:text-red-400 space-y-1">
              {accessibilityOptions.lowContrast && <li>• Low contrast text (light gray on white background)</li>}
              {accessibilityOptions.missingAltText && <li>• Images without alternative text</li>}
              {accessibilityOptions.noStructure && <li>• Missing document structure and tagging</li>}
              {accessibilityOptions.rasterizedText && <li>• Rasterized text (not selectable or searchable)</li>}
              {accessibilityOptions.improperHeadings && <li>• Improper heading hierarchy</li>}
              {accessibilityOptions.noLanguage && <li>• No language declaration</li>}
            </ul>
          </div>
        )}
      </div>
    </div>
  )
}
