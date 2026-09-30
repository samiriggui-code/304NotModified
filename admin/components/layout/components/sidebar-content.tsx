'use client';

import { SidebarDefaultContent } from './sidebar-default-content';
import { SidebarDefaultHeader } from './sidebar-default-header';

export function SidebarContent() {
  return (
    <>
      <SidebarDefaultHeader />
      <SidebarDefaultContent />
    </>
  );
}
