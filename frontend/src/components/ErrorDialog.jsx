import { useEffect, useRef } from "react"

const FOCUSABLE_ELEMENTS_SELECTOR = "button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])"

export default function ErrorDialog({ title, message, closeText = "OK", onClose }) {
  const dialogRef = useRef(null)

  useEffect(() => {
    if (typeof document === "undefined") {
      return undefined
    }
    const handleKeyDown = (event) => {
      if (event.key === "Escape") {
        onClose()
      }
    }
    const getFocusableElements = () => {
      const element = dialogRef.current
      if (!element) {
        return []
      }
      return Array.from(element.querySelectorAll(FOCUSABLE_ELEMENTS_SELECTOR)).filter(
        (node) => !node.hasAttribute("disabled") && node.tabIndex !== -1 && !node.hidden
      )
    }

    const handleTabKey = (event) => {
      if (event.key !== "Tab") {
        return
      }
      const elements = getFocusableElements()
      if (elements.length === 0) {
        event.preventDefault()
        return
      }
      const firstFocusable = elements[0]
      const lastFocusable = elements[elements.length - 1]
      if (event.shiftKey) {
        if (
          document.activeElement === firstFocusable ||
          !dialogRef.current?.contains(document.activeElement)
        ) {
          event.preventDefault()
          lastFocusable.focus()
        }
      } else if (
        document.activeElement === lastFocusable ||
        !dialogRef.current?.contains(document.activeElement)
      ) {
        event.preventDefault()
        firstFocusable.focus()
      }
    }

    const cleanup = () => {
      document.body.style.overflow = "unset"
      document.removeEventListener("keydown", handleKeyDown)
      document.removeEventListener("keydown", handleTabKey)
    }

    document.body.style.overflow = "hidden"
    document.addEventListener("keydown", handleKeyDown)
    document.addEventListener("keydown", handleTabKey)
    const focusable = getFocusableElements()
    if (focusable.length > 0) {
      focusable[0].focus()
    }

    return cleanup
  }, [onClose])

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="error-dialog-title"
      aria-describedby="error-dialog-description"
    >
      <div
        ref={dialogRef}
        className="bg-white dark:bg-slate-900 rounded-2xl shadow-2xl max-w-md w-full p-6 space-y-4"
      >
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-full bg-rose-50 text-rose-600 flex items-center justify-center">
            <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01" />
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
          </div>
          <div className="flex-1 min-w-0">
            <h3 id="error-dialog-title" className="text-lg font-semibold text-slate-900 dark:text-white">
              {title}
            </h3>
            <p id="error-dialog-description" className="text-sm text-slate-600 dark:text-slate-300 whitespace-pre-wrap">
              {message}
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="w-full rounded-lg bg-rose-600 px-4 py-2 text-center text-sm font-semibold text-white transition hover:bg-rose-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-rose-500 dark:focus:ring-offset-slate-800"
        >
          {closeText}
        </button>
      </div>
    </div>
  )
}
