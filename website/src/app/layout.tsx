import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Unfork Open Source | Developer-First AI Infrastructure',
  description: 'We build high-performance, open-source AI infrastructure tools. Decibench — the open testing standard for voice AI agents.',
  icons: {
    icon: '/logo.png',
  },
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet" />
      </head>
      <body>{children}</body>
    </html>
  )
}
