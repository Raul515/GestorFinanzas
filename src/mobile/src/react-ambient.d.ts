/**
 * Tipos ambientales para React, ReactDOM y JSX.
 * Permite que el IDE (VS Code / TypeScript / Pyright) reconozca la sintaxis de React y JSX
 * sin necesidad de tener descargada la carpeta node_modules localmente.
 */

declare module "react" {
  export type ReactNode = any;
  export type FC<P = {}> = (props: P) => any;
  export function useState<T>(initialState: T | (() => T)): [T, (newState: T | ((prev: T) => T)) => void];
  export function useEffect(effect: () => void | (() => void), deps?: any[]): void;
  export function useCallback<T extends (...args: any[]) => any>(callback: T, deps: any[]): T;
  export function useMemo<T>(factory: () => T, deps: any[]): T;
  export function useRef<T>(initialValue?: T): { current: T };
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
