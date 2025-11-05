import { useNotification } from "../contexts/NotificationContext"
import Toast from "./Toast"
import ConfirmDialog from "./ConfirmDialog"

export default function NotificationContainer() {
  const { toasts, confirmDialog, removeToast } = useNotification()

  return (
    <>
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
    </>
  )
}
