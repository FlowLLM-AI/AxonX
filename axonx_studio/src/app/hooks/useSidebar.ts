import { useState } from "react";

const DEFAULT_WIDTH = 248;

function savedWidth() {
  const value = Number(localStorage.getItem("axonx-sidebar-width"));
  return value >= 190 && value <= 360 ? value : DEFAULT_WIDTH;
}

export function useSidebar() {
  const [collapsed, setCollapsed] = useState(
    () => localStorage.getItem("axonx-sidebar") === "collapsed",
  );
  const [width, setWidth] = useState(savedWidth);
  const [mobileOpen, setMobileOpen] = useState(false);

  const toggle = () =>
    setCollapsed((current) => {
      localStorage.setItem("axonx-sidebar", current ? "expanded" : "collapsed");
      return !current;
    });

  const resize = (nextWidth: number) => {
    if (collapsed) setCollapsed(false);
    setWidth(nextWidth);
  };

  const finishResize = (nextWidth: number) => {
    if (nextWidth < 160) {
      setCollapsed(true);
      setWidth(savedWidth());
      localStorage.setItem("axonx-sidebar", "collapsed");
      return;
    }
    setCollapsed(false);
    setWidth(nextWidth);
    localStorage.setItem("axonx-sidebar-width", String(nextWidth));
    localStorage.setItem("axonx-sidebar", "expanded");
  };

  return {
    collapsed,
    width,
    mobileOpen,
    setMobileOpen,
    toggle,
    resize,
    finishResize,
  };
}
