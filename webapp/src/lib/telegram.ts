// Minimal typing of the Telegram WebApp object we use.
// Full schema: https://core.telegram.org/bots/webapps#initializing-mini-apps

export interface TelegramWebApp {
  initData: string;
  initDataUnsafe: { user?: { id: number; first_name?: string } };
  colorScheme: "light" | "dark";
  themeParams: Record<string, string>;
  ready(): void;
  expand(): void;
  close(): void;
  HapticFeedback?: {
    impactOccurred(style: "light" | "medium" | "heavy"): void;
    notificationOccurred(type: "success" | "warning" | "error"): void;
  };
  MainButton?: {
    text: string;
    show(): void;
    hide(): void;
    onClick(cb: () => void): void;
    setText(text: string): void;
  };
}

declare global {
  interface Window {
    Telegram?: { WebApp?: TelegramWebApp };
  }
}

export function tg(): TelegramWebApp | undefined {
  return window.Telegram?.WebApp;
}

export function initTelegram() {
  const w = tg();
  if (w) {
    w.ready();
    w.expand();
  }
}

export function haptic(kind: "light" | "medium" | "heavy" = "light") {
  tg()?.HapticFeedback?.impactOccurred(kind);
}
