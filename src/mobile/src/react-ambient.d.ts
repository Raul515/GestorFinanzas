/**
 * Tipos ambientales para React, ReactDOM y JSX.
 * Permite que el IDE (VS Code / TypeScript / Pyright) reconozca la sintaxis de React y JSX
 * sin necesidad de tener descargada la carpeta node_modules localmente.
 */

declare module "react" {
  export type ReactNode = any;
  export type FC<P = {}> = (props: P, context?: any) => any;
  export type FunctionComponent<P = {}> = (props: P, context?: any) => any;
  export interface ChangeEvent<T = any> {
    target: { value: string } & T;
  }
  export interface MouseEvent<T = any> {
    clientX: number;
    clientY: number;
    preventDefault(): void;
    stopPropagation(): void;
    [key: string]: any;
  }
  export interface KeyboardEvent<T = any> {
    key: string;
    preventDefault(): void;
    stopPropagation(): void;
  }
  export interface Touch {
    clientX: number;
    clientY: number;
    [key: string]: any;
  }
  export interface TouchEvent<T = any> {
    touches: Touch[];
    targetTouches: Touch[];
    changedTouches: Touch[];
    preventDefault(): void;
    stopPropagation(): void;
    [key: string]: any;
  }
  export function useState<T>(initialState: T | (() => T)): [T, (newState: T | ((prev: T) => T)) => void];
  export function useEffect(effect: () => void | (() => void), deps?: any[]): void;
  export function useCallback<T extends (...args: any[]) => any>(callback: T, deps: any[]): T;
  export function useMemo<T>(factory: () => T, deps: any[]): T;
  export function useRef<T>(initialValue: T): { current: T };
  export function useRef<T>(initialValue: T | null): { current: T | null };
  export function useRef<T>(initialValue?: T): { current: T | undefined };
  export const StrictMode: FC<{ children?: any }>;
  const React: any;
  export default React;
}

declare module "react-dom/client" {
  export interface Root {
    render(children: any): void;
    unmount(): void;
  }
  export function createRoot(container: Element | DocumentFragment | null): Root;
}

declare module "react/jsx-runtime" {
  export const jsx: any;
  export const jsxs: any;
  export const Fragment: any;
  export namespace JSX {
    interface IntrinsicElements {
      [elemName: string]: any;
    }
    interface Element extends any {}
  }
}

declare module "react/jsx-dev-runtime" {
  export const jsxDEV: any;
  export const Fragment: any;
  export namespace JSX {
    interface IntrinsicElements {
      [elemName: string]: any;
    }
    interface Element extends any {}
  }
}

declare global {
  namespace React {
    type TouchEvent = any;
    type MouseEvent = any;
    type ChangeEvent = any;
    type KeyboardEvent = any;
    type ReactNode = any;
  }
  namespace JSX {
    interface IntrinsicElements {
      [elemName: string]: any;
    }
    interface Element extends any {}
  }
}

declare module "lucide-react" {
  export const Zap: any;
  export const ListOrdered: any;
  export const Search: any;
  export const X: any;
  export const Check: any;
  export const CheckCircle2: any;
  export const Calendar: any;
  export const Tag: any;
  export const Delete: any;
  export const Trash2: any;
  export const Clock: any;
  export const RefreshCw: any;
  export const Download: any;
  export const ArrowUpRight: any;
  export const Plus: any;
  export const ShieldAlert: any;
  export const ShieldCheck: any;
  export const KeyRound: any;
  export const AlertTriangle: any;
  export const Sparkles: any;
  export const Edit3: any;
  export const TrendingUp: any;
  export const PieChart: any;
  export const BarChart3: any;
  export const Camera: any;
  export const Image: any;
  export const FileText: any;
  export const RotateCcw: any;
  export const Settings: any;
  export const Settings2: any;
  export const Server: any;
}

declare namespace NodeJS {
  type Timeout = any;
}

declare module "vite" {
  export function defineConfig(config: any): any;
}

declare module "@vitejs/plugin-react" {
  const plugin: any;
  export default plugin;
}

declare module "@capacitor/cli" {
  export interface CapacitorConfig {
    appId?: string;
    appName?: string;
    webDir?: string;
    server?: any;
    android?: any;
    [key: string]: any;
  }
}

declare module "@capacitor/core" {
  export const Capacitor: {
    isNativePlatform(): boolean;
    getPlatform(): string;
  };
}

declare module "@capacitor/browser" {
  export const Browser: {
    open(options: { url: string }): Promise<void>;
  };
}

declare module "@capacitor/filesystem" {
  export enum Directory {
    Documents = "DOCUMENTS",
    Data = "DATA",
    Library = "LIBRARY",
    Cache = "CACHE",
    External = "EXTERNAL",
    ExternalStorage = "EXTERNAL_STORAGE",
  }
  export enum Encoding {
    UTF8 = "utf8",
    ASCII = "ascii",
    UTF16 = "utf16",
  }
  export const Filesystem: {
    writeFile(options: { path: string; data: string; directory?: Directory; encoding?: Encoding }): Promise<{ uri: string }>;
  };
}

declare module "@capacitor/share" {
  export const Share: {
    share(options: { title?: string; text?: string; url?: string; files?: string[]; dialogTitle?: string }): Promise<{ activityType?: string }>;
  };
}

declare module "*.css" {
  const content: any;
  export default content;
}

declare const __APP_VERSION__: string;
