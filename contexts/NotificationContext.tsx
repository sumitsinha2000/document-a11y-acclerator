import { createContext, useContext, useState, useCallback, type ReactNode } from "react"
import Toast from "@/components/frontend/Toast"
import ConfirmDialog from "@/components/frontend/ConfirmDialog"

interface ToastData {
  id: number
  message: string
  type: "info" | "success" | "error" | "warning"
  duration: number
}

interface ConfirmDialogData {
  title?: string
  message: string
  confirmText?: string
  cancelText?: string
  onConfirm: () => void
  onCancel: () => void
}

interface NotificationContextType {
  showToast: (message: string, type?: "info" | "success" | "error" | "warning", duration?: number) => void
  showSuccess: (message: string, duration?: number) => void
  showError: (message: string, duration?: number) => void
  showWarning: (message: string, duration?: number) => void
  showInfo: (message: string, duration?: number) => void
  confirm: (options: Omit<ConfirmDialogData, "onConfirm" | "onCancel">) => Promise<boolean>
}

const NotificationContext = createContext<NotificationContextType | null>(null)

export function NotificationProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastData[]>([])
  const [confirmDialog, setConfirmDialog] = useState<ConfirmDialogData | null>(null)

  const showToast = useCallback(
    (message: string, type: "info" | "success" | "error" | "warning" = "info", duration = 5000) => {
      const id = Date.now() + Math.random()
      setToasts((prev) => [...prev, { id, message, type, duration }])
    },
    [],
  )

  const showSuccess = useCallback(
    (message: string, duration?: number) => showToast(message, "success", duration),
    [showToast],
  )
  const showError = useCallback(
    (message: string, duration?: number) => showToast(message, "error", duration),
    [showToast],
  )
  const showWarning = useCallback(
    (message: string, duration?: number) => showToast(message, "warning", duration),
    [showToast],
  )
  const showInfo = useCallback(
    (message: string, duration?: number) => showToast(message, "info", duration),
    [showToast],
  )

  const removeToast = useCallback((id: number) => {
    setToasts((prev) => prev.filter((toast) => toast.id !== id))
  }, [])

  const confirm = useCallback((options: Omit<ConfirmDialogData, "onConfirm" | "onCancel">) => {
    return new Promise<boolean>((resolve) => {
      setConfirmDialog({
        ...options,
        onConfirm: () => {
          setConfirmDialog(null)
          resolve(true)
        },
        onCancel: () => {
          setConfirmDialog(null)
          resolve(false)
        },
      })
    })
  }, [])

  return (
    <NotificationContext.Provider
      value={{
        showToast,
        showSuccess,
        showError,
        showWarning,
        showInfo,
        confirm,
      }}
    >
      {children}

      {/* Toast Container */}
      <div className="fixed top-4 right-4 z-50 flex flex-col gap-3 max-w-md w-full pointer-events-none">
        <div className="flex flex-col gap-3 pointer-events-auto">
          {toasts.map((toast) => (
            <Toast
              key={toast.id}
              message={toast.message}
              type={toast.type}
              duration={toast.duration}
              onClose={() => removeToast(toast.id)}
            />
          ))}
        </div>
      </div>

      {/* Confirm Dialog */}
      {confirmDialog && <ConfirmDialog {...confirmDialog} />}
    </NotificationContext.Provider>
  )
}

export function useNotification() {
  const context = useContext(NotificationContext)
  if (!context) {
    throw new Error("useNotification must be used within a NotificationProvider")
  }
  return context
}
