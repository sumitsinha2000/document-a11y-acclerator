import { ReactNode, useEffect } from 'react';

type ToastType = 'success' | 'error' | 'warning' | 'info';

interface ToastProps {
  message: string;
  type?: ToastType;
  duration?: number;
  onClose: () => void;
}

const TYPE_STYLES: Record<
  ToastType,
  {
    title: string;
    icon: ReactNode;
    accentBar: string;
    border: string;
    iconBg: string;
    text: string;
    subText: string;
  }
> = {
  success: {
    title: 'Success',
    accentBar: 'bg-emerald-500',
    border: 'border-emerald-100/70',
    iconBg: 'bg-emerald-500/15 text-emerald-600',
    text: 'text-emerald-900',
    subText: 'text-emerald-800/80',
    icon: (
      <svg className="h-9 w-9" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} aria-hidden="true">
        <circle cx="12" cy="12" r="9" strokeOpacity={0.9} />
        <path d="M8.5 12.5l2.5 2.5 4.5-5.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
  error: {
    title: 'Something went wrong',
    accentBar: 'bg-rose-500',
    border: 'border-rose-100/70',
    iconBg: 'bg-rose-500/15 text-rose-600',
    text: 'text-rose-900',
    subText: 'text-rose-800/80',
    icon: (
      <svg className="h-9 w-9" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} aria-hidden="true">
        <circle cx="12" cy="12" r="9" strokeOpacity={0.9} />
        <path d="M9 9l6 6m0-6-6 6" strokeLinecap="round" />
      </svg>
    ),
  },
  warning: {
    title: 'Heads up',
    accentBar: 'bg-amber-500',
    border: 'border-amber-100/70',
    iconBg: 'bg-amber-500/15 text-amber-600',
    text: 'text-amber-900',
    subText: 'text-amber-800/80',
    icon: (
      <svg className="h-9 w-9" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} aria-hidden="true">
        <path d="M12 4l8 14H4l8-14z" strokeLinejoin="round" strokeOpacity={0.9} />
        <path d="M12 10v3.5" strokeLinecap="round" />
        <circle cx="12" cy="16.5" r="0.9" fill="currentColor" stroke="none" />
      </svg>
    ),
  },
  info: {
    title: 'FYI',
    accentBar: 'bg-sky-500',
    border: 'border-sky-100/70',
    iconBg: 'bg-sky-500/15 text-sky-600',
    text: 'text-sky-900',
    subText: 'text-sky-800/80',
    icon: (
      <svg className="h-9 w-9" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} aria-hidden="true">
        <circle cx="12" cy="12" r="9" strokeOpacity={0.9} />
        <path d="M12 10.5v5" strokeLinecap="round" />
        <circle cx="12" cy="8" r="0.9" fill="currentColor" stroke="none" />
      </svg>
    ),
  },
};

const Toast = ({ message, type = 'info', duration = 5000, onClose }: ToastProps) => {
  useEffect(() => {
    if (duration > 0) {
      const timer = setTimeout(() => {
        onClose();
      }, duration);
      return () => clearTimeout(timer);
    }
  }, [duration, onClose]);

  const style = TYPE_STYLES[type] ?? TYPE_STYLES.info;
  const liveRegion = type === 'error' || type === 'warning' ? 'assertive' : 'polite';

  return (
    <div
      className={`group relative flex w-full min-w-[280px] max-w-md items-start gap-4 overflow-hidden rounded-2xl border bg-white/95 p-4 shadow-xl ring-1 ring-black/5 backdrop-blur ${style.border}`}
      role={liveRegion === 'assertive' ? 'alert' : 'status'}
      aria-live={liveRegion}
      data-toast-type={type}
    >
      <span className="sr-only">{style.title}</span>
      <div className={`flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-full ${style.iconBg}`}>{style.icon}</div>
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <p className={`text-sm font-semibold ${style.text}`}>{style.title}</p>
        <p className={`text-sm leading-relaxed ${style.subText} whitespace-pre-line`}>{message}</p>
      </div>
      <button
        onClick={onClose}
        className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full text-gray-500 transition hover:bg-gray-100 hover:text-gray-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-gray-400"
        aria-label="Close notification"
      >
        <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 6l12 12M18 6L6 18" />
        </svg>
      </button>
    </div>
  );
};

export default Toast;
