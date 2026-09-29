import type { ComponentType, ReactNode } from "react";

export type GlideSelectOption = string | { value: string; label: ReactNode; tag?: string };

export type GlideSelectProps = {
  options?: GlideSelectOption[];
  value?: string;
  defaultValue?: string;
  onChange?: (value: string, option: Exclude<GlideSelectOption, string>) => void;
  placeholder?: string;
  showTags?: boolean;
  accentColor?: string;
  surfaceColor?: string;
  highlightColor?: string;
  textColor?: string;
  size?: "sm" | "md" | "lg";
  radius?: number;
  menuWidth?: number;
  placement?: "top" | "bottom";
  align?: "left" | "right";
  popDuration?: number;
  glideDuration?: number;
  rememberPosition?: boolean;
  disabled?: boolean;
  ariaLabel?: string;
  className?: string;
};

declare const GlideSelect: ComponentType<GlideSelectProps>;
export default GlideSelect;
