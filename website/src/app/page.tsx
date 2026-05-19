'use client';

import React from 'react';
import { motion } from 'framer-motion';
import Link from 'next/link';
import { ArrowRight, Globe, Terminal, Shield, Sparkles, BookOpen } from 'lucide-react';

const GithubIcon = ({ size = 16 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor"><path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"/></svg>
);

const fadeUp = {
  initial: { opacity: 0, y: 30 },
  animate: { opacity: 1, y: 0 },
};

export default function Home() {
  return (
    <main style={{ minHeight: '100vh', position: 'relative' }}>

      {/* ─── Nav ─── */}
      <nav className="nav">
        <Link href="/" className="nav-brand">
          <img src="/unfork-logo.png" alt="Unfork" style={{ width: '32px', height: '32px', borderRadius: '6px' }} />
          <span>unfork</span>
        </Link>
        <div className="nav-links">
          <Link href="/decibench" className="nav-link">Decibench</Link>
          <a href="https://github.com/unforkopensource-org" target="_blank" rel="noopener noreferrer" className="nav-link">GitHub</a>
        </div>
      </nav>

      {/* ─── Hero ─── */}
      <section className="unfork-hero">
        <motion.div {...fadeUp} transition={{ duration: 0.8 }}>
          <div className="section-label">Open Source</div>

          <h1>
            We build tools<br />
            <span className="gradient-text">developers trust.</span>
          </h1>

          <p className="tagline">
            Unfork is an open-source collective building high-performance infrastructure for the AI era. Local-first. Zero telemetry. No vendor lock-in.
          </p>

          <div style={{ display: 'flex', gap: '1rem', justifyContent: 'center', flexWrap: 'wrap' }}>
            <Link href="/decibench" className="btn-primary">
              Explore Decibench <ArrowRight size={16} />
            </Link>
            <a href="https://github.com/unforkopensource-org" target="_blank" rel="noopener noreferrer" className="btn-ghost">
              <GithubIcon size={16} /> GitHub
            </a>
          </div>
        </motion.div>
      </section>

      {/* ─── Products ─── */}
      <section className="section">
        <div className="section-inner">
          <motion.div {...fadeUp} transition={{ duration: 0.6 }} viewport={{ once: true }} whileInView="animate" initial="initial">
            <div className="section-label">Products</div>
            <h2 className="section-title">Ship with confidence.</h2>
            <p className="section-desc" style={{ marginBottom: '4rem' }}>
              Every tool we build solves a real problem we faced while building AI systems in production.
            </p>
          </motion.div>

          {/* Decibench Product Card */}
          <motion.div {...fadeUp} transition={{ duration: 0.6, delay: 0.2 }} viewport={{ once: true }} whileInView="animate" initial="initial">
            <Link href="/decibench" style={{ textDecoration: 'none' }}>
              <div className="product-card">
                <div className="product-card-info">
                  <div style={{ display: 'flex', gap: '8px', marginBottom: '1.5rem', flexWrap: 'wrap' }}>
                    <span className="product-tag" style={{ background: 'rgba(0,240,255,0.1)', color: 'var(--cyan)' }}>Voice AI</span>
                    <span className="product-tag" style={{ background: 'rgba(57,255,20,0.1)', color: 'var(--green)' }}>Testing</span>
                    <span className="product-tag" style={{ background: 'rgba(138,43,226,0.1)', color: 'var(--purple)' }}>v1.0.0</span>
                  </div>
                  <h3>Decibench</h3>
                  <p>
                    The open testing standard for voice AI agents. Simulate thousands of calls, detect 100% of hallucinations, and score latency down to the millisecond. Works with Vapi, Retell, ElevenLabs, Twilio, and any WebSocket endpoint.
                  </p>
                  <span className="btn-ghost" style={{ display: 'inline-flex' }}>
                    Learn more <ArrowRight size={14} />
                  </span>
                </div>

                <div className="product-card-visual">
                  <div><span className="comment"># Install from source</span></div>
                  <div><span className="cmd">$</span> pip install git+https://github.com/unforkopensource-org/decibench.git</div>
                  <br />
                  <div><span className="comment"># Run your first test</span></div>
                  <div><span className="cmd">$</span> decibench run target=demo suite=quick</div>
                  <br />
                  <div><span className="output">✓ 10/10 scenarios passed</span></div>
                  <div><span className="output">  Score: 94/100</span></div>
                  <div><span className="output">  Latency p95: 420ms</span></div>
                  <div><span className="output">  Hallucinations: 0</span></div>
                </div>
              </div>
            </Link>
          </motion.div>

          {/* Coming Soon Card */}
          <motion.div {...fadeUp} transition={{ duration: 0.6, delay: 0.3 }} viewport={{ once: true }} whileInView="animate" initial="initial" style={{ marginTop: '1.5rem' }}>
            <div className="glass-card" style={{ padding: '2.5rem', opacity: 0.5, textAlign: 'center' }}>
              <p style={{ color: 'var(--text-muted)', fontSize: '0.95rem' }}>
                More products coming soon. We are building in public.
              </p>
            </div>
          </motion.div>
        </div>
      </section>

      {/* ─── What is Unfork ─── */}
      <section className="section" style={{ borderTop: '1px solid var(--border)' }}>
        <div className="section-inner">
          <motion.div {...fadeUp} transition={{ duration: 0.6 }} viewport={{ once: true }} whileInView="animate" initial="initial">
            <div className="section-label">About</div>
            <h2 className="section-title">What is Unfork?</h2>
            <p className="section-desc">
              We&apos;re a collective of engineers who got tired of building on top of fragile, closed-source AI infrastructure. So we started building our own — and open-sourcing everything.
            </p>
          </motion.div>

          <div className="about-grid">
            <motion.div className="about-item" {...fadeUp} transition={{ duration: 0.5, delay: 0.1 }} viewport={{ once: true }} whileInView="animate" initial="initial">
              <Terminal size={24} color="var(--cyan)" style={{ marginBottom: '1rem' }} />
              <h4>Developer-First</h4>
              <p>CLI tools, not dashboards. Config files, not drag-and-drop. We build for engineers who ship from the terminal.</p>
            </motion.div>

            <motion.div className="about-item" {...fadeUp} transition={{ duration: 0.5, delay: 0.2 }} viewport={{ once: true }} whileInView="animate" initial="initial">
              <Shield size={24} color="var(--green)" style={{ marginBottom: '1rem' }} />
              <h4>Local-First</h4>
              <p>Your data stays on your machine. Zero telemetry. Zero cloud dependencies. Run air-gapped if you want.</p>
            </motion.div>

            <motion.div className="about-item" {...fadeUp} transition={{ duration: 0.5, delay: 0.3 }} viewport={{ once: true }} whileInView="animate" initial="initial">
              <BookOpen size={24} color="var(--purple)" style={{ marginBottom: '1rem' }} />
              <h4>Truly Open</h4>
              <p>Apache 2.0 licensed. No &ldquo;open core&rdquo; bait-and-switch. The full product is the open-source product.</p>
            </motion.div>

            <motion.div className="about-item" {...fadeUp} transition={{ duration: 0.5, delay: 0.4 }} viewport={{ once: true }} whileInView="animate" initial="initial">
              <Sparkles size={24} color="var(--pink)" style={{ marginBottom: '1rem' }} />
              <h4>Built in Public</h4>
              <p>Every commit, every decision, every architecture doc is public. We don&apos;t hide behind private repos.</p>
            </motion.div>
          </div>
        </div>
      </section>

      {/* ─── Footer ─── */}
      <footer className="footer">
        <div style={{ marginBottom: '1rem' }}>
          <a href="https://github.com/unforkopensource-org" target="_blank" rel="noopener noreferrer" className="nav-link" style={{ marginRight: '2rem' }}>GitHub</a>
          <Link href="/decibench" className="nav-link">Decibench</Link>
        </div>
        <p>© 2026 Unfork Open Source. All tools are Apache 2.0 licensed.</p>
      </footer>

    </main>
  );
}
