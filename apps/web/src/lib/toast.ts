import { useEffect, useState } from "react";

export type ToastType = "success" | "error" | "info" | "warning";

export interface ToastMessage {
  id: string;
  type: ToastType;
  title?: string;
  message: string;
  duration?: number;
}

type Listener = (toasts: ToastMessage[]) => void;

let toasts: ToastMessage[] = [];
const listeners: Set<Listener> = new Set();

function notify() {
  for (const listener of listeners) {
    listener([...toasts]);
  }
}

export const toast = {
  show: (message: string, type: ToastType = "info", options?: { title?: string; duration?: number }) => {
    const id = Math.random().toString(36).substring(2, 9);
    const duration = options?.duration ?? 4000;
    const item: ToastMessage = {
      id,
      type,
      message,
      title: options?.title,
      duration,
    };
    toasts = [item, ...toasts].slice(0, 5); // Keep max 5 toasts
    notify();

    if (duration > 0) {
      setTimeout(() => {
        toast.dismiss(id);
      }, duration);
    }
    return id;
  },
  success: (message: string, options?: { title?: string; duration?: number }) => {
    return toast.show(message, "success", options);
  },
  error: (message: string, options?: { title?: string; duration?: number }) => {
    return toast.show(message, "error", options);
  },
  warning: (message: string, options?: { title?: string; duration?: number }) => {
    return toast.show(message, "warning", options);
  },
  info: (message: string, options?: { title?: string; duration?: number }) => {
    return toast.show(message, "info", options);
  },
  dismiss: (id: string) => {
    toasts = toasts.filter((t) => t.id !== id);
    notify();
  },
};

export function useToasts(): ToastMessage[] {
  const [current, setCurrent] = useState<ToastMessage[]>(toasts);

  useEffect(() => {
    listeners.add(setCurrent);
    return () => {
      listeners.delete(setCurrent);
    };
  }, []);

  return current;
}
