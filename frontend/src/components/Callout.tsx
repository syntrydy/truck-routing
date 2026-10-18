import type { ReactNode } from "react";

import { AlertIcon, InfoIcon, StormIcon, WarnIcon } from "./icons.tsx";

export type CalloutTone = "info" | "caution" | "danger" | "demo";

const ICONS: Record<CalloutTone, () => ReactNode> = {
  info: InfoIcon,
  caution: WarnIcon,
  danger: AlertIcon,
  demo: StormIcon,
};

interface CalloutProps {
  tone: CalloutTone;
  /** What it is about, in a few words. */
  title: string;
  /** `alert` for what needs attention at once, `status` for what is only good to know. */
  role: "alert" | "status";
  children?: ReactNode;
}

/**
 * The one way the panel tells the user something: a tone (its colour, which never stands
 * alone), an icon, a title and a few words. The demo notice, the warnings, the errors and the
 * server's state all use it, so that they look like one family.
 */
export function Callout({ tone, title, role, children }: CalloutProps) {
  const Icon = ICONS[tone];
  return (
    <div className={`callout callout--${tone}`} role={role}>
      <span className="callout__icon">
        <Icon />
      </span>
      <div className="callout__body">
        <p className="callout__title">{title}</p>
        {children}
      </div>
    </div>
  );
}
