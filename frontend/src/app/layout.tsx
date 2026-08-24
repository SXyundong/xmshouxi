import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: '电商多部门 Agent 系统',
  description: '电商公司多部门 AI Agent 系统 V1',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
