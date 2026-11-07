import { forwardRef, type ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost";
  size?: "default" | "icon";
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { className, variant = "secondary", size = "default", ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      className={cn("button", `button-${variant}`, size === "icon" && "button-icon", className)}
      {...props}
    />
  );
});
