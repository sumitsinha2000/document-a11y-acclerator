import { useNotification } from "../contexts/NotificationContext"
import Toast from "./Toast"
import ConfirmDialog from "./ConfirmDialog"
import ErrorDialog from "./ErrorDialog"

export default function NotificationContainer() {
  const { toasts, confirmDialog, dialog, removeToast } = useNotification()

  const hasToasts = toasts && toasts.length > 0

  return (
    <>
      {/* Toast Container (live region) */}
      {hasToasts && (
        <div
          className="fixed top-4 right-4 z-50 flex flex-col gap-3 max-w-md w-full pointer-events-none"
          // Live region for assistive tech
          aria-live="polite"
          aria-atomic="true"
        >
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
      )}

      {/* Confirm Dialog */}
      {confirmDialog && <ConfirmDialog {...confirmDialog} />}
      {/* Error Dialog */}
      {dialog && <ErrorDialog {...dialog} />}
    </>
  )
}
