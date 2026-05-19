'use client';

import React from 'react';
import { motion } from 'framer-motion';
import Link from 'next/link';
import { Activity, ShieldAlert, Cpu, ArrowLeft, Zap, Mic, Brain, Eye, Timer, AudioLines, BarChart3, ShieldCheck, VolumeX } from 'lucide-react';
import Hero3D from '../../components/Hero3D';

const GithubIcon = ({ size = 16 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor"><path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"/></svg>
);

const fadeUp = {
  initial: { opacity: 0, y: 30 },
  animate: { opacity: 1, y: 0 },
};

export default function DecibenchPage() {
  return (
    <main style={{ minHeight: '100vh', position: 'relative', overflow: 'hidden' }}>
      <Hero3D />

      {/* ─── Nav ─── */}
      <nav className="nav" style={{ borderBottom: 'none' }}>
        <Link href="/" className="nav-brand">
          <img src="/unfork-logo.png" alt="Unfork" style={{ width: '32px', height: '32px', borderRadius: '6px' }} />
          <span>unfork <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}>/</span> decibench</span>
        </Link>
        <div className="nav-links">
          <Link href="/" className="nav-link"><ArrowLeft size={14} style={{ marginRight: '4px' }} /> Unfork</Link>
          <a href="https://github.com/unforkopensource-org/decibench" target="_blank" rel="noopener noreferrer" className="nav-link"><GithubIcon size={14} /> GitHub</a>
        </div>
      </nav>

      {/* ─── Hero ─── */}
      <section className="unfork-hero" style={{ minHeight: 'calc(100vh - 80px)' }}>
        <motion.div {...fadeUp} transition={{ duration: 0.8 }}>
          <div className="section-label">v1.0.0 · Open Source · Apache 2.0</div>

          <h1>
            Unit Testing for the<br />
            <span className="gradient-text">Voice AI Era</span>
          </h1>

          <p className="tagline">
            Simulate thousands of concurrent calls. Detect hallucinations instantly. Score latency down to the millisecond. Works with any voice agent.
          </p>

          <div style={{ display: 'flex', gap: '1rem', justifyContent: 'center', flexWrap: 'wrap' }}>
            <a href="https://github.com/unforkopensource-org/decibench" target="_blank" rel="noopener noreferrer" className="btn-primary">
              <GithubIcon size={16} /> Get Started
            </a>
            <a href="#features" className="btn-ghost">
              See Features
            </a>
          </div>

          {/* Install command */}
          <div style={{
            marginTop: '3rem',
            background: 'rgba(255,255,255,0.03)',
            border: '1px solid var(--glass-border)',
            borderRadius: '10px',
            padding: '0.75rem 1.5rem',
            fontFamily: "'SF Mono', 'Fira Code', monospace",
            fontSize: '0.85rem',
            color: 'var(--text-secondary)',
            display: 'inline-block'
          }}>
            <span style={{ color: 'var(--cyan)' }}>$</span> pip install git+https://github.com/unforkopensource-org/decibench.git
          </div>
        </motion.div>
      </section>

      {/* ─── Stats ─── */}
      <div className="stats-row">
        <div>
          <div className="stat-value" style={{ color: 'var(--cyan)' }}>10</div>
          <div className="stat-label">Built-in Evaluators</div>
        </div>
        <div>
          <div className="stat-value" style={{ color: 'var(--green)' }}>8</div>
          <div className="stat-label">Connectors Shipped</div>
        </div>
        <div>
          <div className="stat-value" style={{ color: 'var(--purple)' }}>3</div>
          <div className="stat-label">Testing Modes</div>
        </div>
        <div>
          <div className="stat-value" style={{ color: 'var(--pink)' }}>0</div>
          <div className="stat-label">Telemetry Calls</div>
        </div>
      </div>

      {/* ─── How It Works ─── */}
      <section className="section">
        <div className="section-inner">
          <motion.div {...fadeUp} transition={{ duration: 0.6 }} viewport={{ once: true }} whileInView="animate" initial="initial">
            <div className="section-label">How it works</div>
            <h2 className="section-title">Write YAML. Run tests. Ship.</h2>
            <p className="section-desc" style={{ marginBottom: '3rem' }}>
              Decibench synthesizes caller audio, calls your agent over any protocol, transcribes the response, and scores it across 10 metrics — all from one command.
            </p>
          </motion.div>

          <motion.div {...fadeUp} transition={{ duration: 0.6, delay: 0.2 }} viewport={{ once: true }} whileInView="animate" initial="initial">
            <div className="product-card-visual" style={{ maxWidth: '700px', fontSize: '0.9rem', lineHeight: 2 }}>
              <div><span className="comment"># 1. Install</span></div>
              <div><span className="cmd">$</span> pip install git+https://github.com/unforkopensource-org/decibench.git</div>
              <br />
              <div><span className="comment"># 2. Test the built-in demo agent (zero config)</span></div>
              <div><span className="cmd">$</span> decibench run target=demo suite=quick</div>
              <br />
              <div><span className="comment"># 3. Test YOUR agent</span></div>
              <div><span className="cmd">$</span> decibench run target=ws://localhost:8080/ws suite=standard</div>
              <br />
              <div><span className="comment"># 4. View results in the dashboard</span></div>
              <div><span className="cmd">$</span> decibench serve</div>
              <div><span className="output">✓ Dashboard running at http://localhost:8100</span></div>
            </div>
          </motion.div>
        </div>
      </section>

      {/* ─── Three Modes ─── */}
      <section id="features" className="section" style={{ borderTop: '1px solid var(--border)' }}>
        <div className="section-inner">
          <motion.div {...fadeUp} transition={{ duration: 0.6 }} viewport={{ once: true }} whileInView="animate" initial="initial">
            <div className="section-label">Testing Modes</div>
            <h2 className="section-title">Three levels of depth.</h2>
          </motion.div>

          <div className="features-grid" style={{ marginTop: '3rem' }}>
            <motion.div className="glass-card" style={{ padding: '2.5rem' }} {...fadeUp} transition={{ duration: 0.5, delay: 0.1 }} viewport={{ once: true }} whileInView="animate" initial="initial">
              <Activity color="var(--cyan)" size={28} style={{ marginBottom: '1.25rem' }} />
              <h3 style={{ fontSize: '1.2rem', fontWeight: 700, marginBottom: '0.75rem' }}>Deterministic</h3>
              <p style={{ color: 'var(--text-secondary)', lineHeight: 1.65, fontSize: '0.95rem', marginBottom: '1rem' }}>
                Exact string matching, regex, keyword checks. Sub-millisecond. Runs entirely locally with zero API costs.
              </p>
              <span style={{ color: 'var(--cyan)', fontSize: '0.8rem', fontWeight: 600 }}>FREE · ~ms per test</span>
            </motion.div>

            <motion.div className="glass-card" style={{ padding: '2.5rem' }} {...fadeUp} transition={{ duration: 0.5, delay: 0.2 }} viewport={{ once: true }} whileInView="animate" initial="initial">
              <Cpu color="var(--green)" size={28} style={{ marginBottom: '1.25rem' }} />
              <h3 style={{ fontSize: '1.2rem', fontWeight: 700, marginBottom: '0.75rem' }}>Semantic</h3>
              <p style={{ color: 'var(--text-secondary)', lineHeight: 1.65, fontSize: '0.95rem', marginBottom: '1rem' }}>
                LLM-as-Judge scores accuracy, compliance, and hallucination rates. Works with GPT-4o, Claude, Gemini, or Ollama.
              </p>
              <span style={{ color: 'var(--green)', fontSize: '0.8rem', fontWeight: 600 }}>~$0.01/call · ~2s per test</span>
            </motion.div>

            <motion.div className="glass-card" style={{ padding: '2.5rem' }} {...fadeUp} transition={{ duration: 0.5, delay: 0.3 }} viewport={{ once: true }} whileInView="animate" initial="initial">
              <ShieldAlert color="var(--purple)" size={28} style={{ marginBottom: '1.25rem' }} />
              <h3 style={{ fontSize: '1.2rem', fontWeight: 700, marginBottom: '0.75rem' }}>RAG-Augmented</h3>
              <p style={{ color: 'var(--text-secondary)', lineHeight: 1.65, fontSize: '0.95rem', marginBottom: '1rem' }}>
                Upload your knowledge base. Decibench auto-generates adversarial test suites that actively try to break your agent.
              </p>
              <span style={{ color: 'var(--purple)', fontSize: '0.8rem', fontWeight: 600 }}>~$0.03/call · ~5s per test</span>
            </motion.div>
          </div>
        </div>
      </section>

      {/* ─── Evaluators ─── */}
      <section className="section" style={{ borderTop: '1px solid var(--border)' }}>
        <div className="section-inner">
          <motion.div {...fadeUp} transition={{ duration: 0.6 }} viewport={{ once: true }} whileInView="animate" initial="initial">
            <div className="section-label">Evaluators</div>
            <h2 className="section-title">10 metrics. Every call.</h2>
            <p className="section-desc" style={{ marginBottom: '3rem' }}>
              Every call is automatically scored across all applicable metrics. No configuration needed.
            </p>
          </motion.div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1rem' }}>
            {[
              { icon: <Timer size={20} />, name: 'Latency', desc: 'p50 / p90 / p95 / TTFB', color: 'var(--cyan)' },
              { icon: <Mic size={20} />, name: 'WER / CER', desc: 'Word & character error rates', color: 'var(--green)' },
              { icon: <Brain size={20} />, name: 'Hallucination', desc: 'LLM-graded factual accuracy', color: 'var(--pink)' },
              { icon: <Zap size={20} />, name: 'Task Completion', desc: 'Did the agent achieve the goal?', color: 'var(--cyan)' },
              { icon: <ShieldCheck size={20} />, name: 'Compliance', desc: 'Mandatory disclosures & disclaimers', color: 'var(--green)' },
              { icon: <AudioLines size={20} />, name: 'Interruption', desc: 'Barge-in handling robustness', color: 'var(--purple)' },
              { icon: <VolumeX size={20} />, name: 'Silence', desc: 'Dead air detection', color: 'var(--pink)' },
              { icon: <Eye size={20} />, name: 'MOS / STOI', desc: 'Audio quality & intelligibility', color: 'var(--cyan)' },
              { icon: <BarChart3 size={20} />, name: 'Composite Score', desc: 'Weighted aggregate — single number', color: 'var(--green)' },
            ].map((item, i) => (
              <motion.div
                key={item.name}
                className="glass-card"
                style={{ padding: '1.25rem 1.5rem', display: 'flex', alignItems: 'center', gap: '1rem' }}
                {...fadeUp}
                transition={{ duration: 0.4, delay: i * 0.05 }}
                viewport={{ once: true }}
                whileInView="animate"
                initial="initial"
              >
                <div style={{ color: item.color, flexShrink: 0 }}>{item.icon}</div>
                <div>
                  <div style={{ fontWeight: 600, fontSize: '0.95rem' }}>{item.name}</div>
                  <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>{item.desc}</div>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ─── Connectors ─── */}
      <section className="section" style={{ borderTop: '1px solid var(--border)' }}>
        <div className="section-inner">
          <motion.div {...fadeUp} transition={{ duration: 0.6 }} viewport={{ once: true }} whileInView="animate" initial="initial">
            <div className="section-label">Connectors</div>
            <h2 className="section-title">Works with your stack.</h2>
            <p className="section-desc" style={{ marginBottom: '3rem' }}>
              No SDK to install in your agent. Decibench connects to your agent — not the other way around.
            </p>
          </motion.div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem' }}>
            {[
              { name: 'WebSocket', uri: 'ws://', status: '✅' },
              { name: 'ElevenLabs', uri: 'elevenlabs://', status: '✅' },
              { name: 'Twilio Mock', uri: 'twilio://', status: '✅' },
              { name: 'HTTP', uri: 'http://', status: '✅' },
              { name: 'Process', uri: 'exec:"…"', status: '✅' },
              { name: 'Vapi', uri: 'vapi://', status: '🧪' },
              { name: 'Retell', uri: 'retell://', status: '🧪' },
              { name: 'LiveKit', uri: '—', status: '📋' },
            ].map((c, i) => (
              <motion.div
                key={c.name}
                className="glass-card"
                style={{ padding: '1.25rem 1.5rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
                {...fadeUp}
                transition={{ duration: 0.4, delay: i * 0.05 }}
                viewport={{ once: true }}
                whileInView="animate"
                initial="initial"
              >
                <div>
                  <div style={{ fontWeight: 600, fontSize: '0.95rem' }}>{c.name}</div>
                  <div style={{ color: 'var(--text-muted)', fontSize: '0.75rem', fontFamily: 'monospace' }}>{c.uri}</div>
                </div>
                <span style={{ fontSize: '1.1rem' }}>{c.status}</span>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ─── CTA ─── */}
      <section className="section" style={{ textAlign: 'center', borderTop: '1px solid var(--border)' }}>
        <div className="section-inner">
          <motion.div {...fadeUp} transition={{ duration: 0.6 }} viewport={{ once: true }} whileInView="animate" initial="initial">
            <h2 className="section-title">Stop testing manually.<br /><span className="gradient-text">Start shipping with confidence.</span></h2>
            <p className="section-desc" style={{ margin: '0 auto 2.5rem auto', textAlign: 'center' }}>
              Decibench is free, open source, and ready for production.
            </p>
            <div style={{ display: 'flex', gap: '1rem', justifyContent: 'center', flexWrap: 'wrap' }}>
              <a href="https://github.com/unforkopensource-org/decibench" target="_blank" rel="noopener noreferrer" className="btn-primary">
                <GithubIcon size={16} /> View on GitHub
              </a>
              <Link href="/" className="btn-ghost">
                <ArrowLeft size={14} /> Back to Unfork
              </Link>
            </div>
          </motion.div>
        </div>
      </section>

      {/* ─── Footer ─── */}
      <footer className="footer">
        <div style={{ marginBottom: '1rem' }}>
          <Link href="/" className="nav-link" style={{ marginRight: '2rem' }}>Unfork</Link>
          <a href="https://github.com/unforkopensource-org/decibench" target="_blank" rel="noopener noreferrer" className="nav-link">GitHub</a>
        </div>
        <p>© 2026 Unfork Open Source. Apache 2.0 Licensed.</p>
      </footer>

    </main>
  );
}
