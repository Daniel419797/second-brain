import Link from 'next/link';
import * as React from 'react';
import { cn } from '@/lib/utils';

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  asChild?: boolean;
  href?: string;
  variant?: 'primary' | 'secondary' | 'ghost';
};

export function Button({ asChild = false, className, href, variant = 'primary', children, ...props }: ButtonProps) {
  const classes = cn('button', `button-${variant}`, className);
  if (asChild && React.isValidElement(children)) {
    return React.cloneElement(children as React.ReactElement<{ className?: string }>, {
      className: cn(classes, (children.props as { className?: string }).className),
    });
  }
  if (href) {
    return <Link className={classes} href={href}>{children}</Link>;
  }
  return <button className={classes} {...props}>{children}</button>;
}
