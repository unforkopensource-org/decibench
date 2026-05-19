import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Decibench | Unit Testing for the Voice AI Era',
  description: 'Simulate thousands of concurrent calls, detect hallucinations, and score latency down to the millisecond.',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}
