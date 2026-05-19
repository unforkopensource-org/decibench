'use client';

import React from 'react';
import { motion } from 'framer-motion';
import { Activity, ShieldAlert, Zap, Cpu, Code2 } from 'lucide-react';
import Hero3D from '../components/Hero3D';

export default function Home() {
  return (
    <main style={{ minHeight: '100vh', position: 'relative', overflow: 'hidden' }}>
      <Hero3D />
      
      {/* Navigation */}
      <nav style={{ padding: '2rem 4rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center', zIndex: 10, position: 'relative' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          {/* Logo imported from the copied asset */}
          <img src="/logo.png" alt="Unfork Logo" style={{ width: '40px', height: '40px' }} />
          <span style={{ fontSize: '1.2rem', fontWeight: 700, letterSpacing: '-0.02em' }}>Decibench</span>
        </div>
        <div style={{ display: 'flex', gap: '2rem', fontSize: '0.9rem', fontWeight: 500 }}>
          <a href="https://github.com/unforkopensource-org/decibench" target="_blank" rel="noopener noreferrer" style={{ transition: 'color 0.2s', color: 'rgba(255,255,255,0.7)' }} onMouseOver={(e) => e.currentTarget.style.color = '#fff'} onMouseOut={(e) => e.currentTarget.style.color = 'rgba(255,255,255,0.7)'}>GitHub</a>
          <a href="https://pypi.org/project/decibench/" target="_blank" rel="noopener noreferrer" style={{ transition: 'color 0.2s', color: 'rgba(255,255,255,0.7)' }} onMouseOver={(e) => e.currentTarget.style.color = '#fff'} onMouseOut={(e) => e.currentTarget.style.color = 'rgba(255,255,255,0.7)'}>PyPI</a>
        </div>
      </nav>

      {/* Hero Content */}
      <section style={{ height: 'calc(100vh - 100px)', display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', textAlign: 'center', padding: '0 2rem', zIndex: 10, position: 'relative' }}>
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8 }}
        >
          <div style={{ display: 'inline-block', padding: '6px 16px', background: 'rgba(0, 240, 255, 0.1)', border: '1px solid rgba(0, 240, 255, 0.2)', borderRadius: '100px', fontSize: '0.85rem', fontWeight: 600, color: 'var(--cyan)', marginBottom: '2rem', letterSpacing: '0.05em' }}>
            UNFORK OPEN SOURCE • v1.0.0
          </div>
          
          <h1 style={{ fontSize: 'clamp(3rem, 8vw, 6rem)', fontWeight: 800, lineHeight: 1.1, letterSpacing: '-0.04em', marginBottom: '1.5rem', maxWidth: '1000px' }}>
            Unit Testing for the <br />
            <span className="gradient-text">Voice AI Era</span>
          </h1>
          
          <p style={{ fontSize: 'clamp(1rem, 2vw, 1.25rem)', color: 'rgba(255,255,255,0.6)', maxWidth: '600px', margin: '0 auto 3rem auto', lineHeight: 1.6, fontWeight: 400 }}>
            Simulate thousands of concurrent calls, detect hallucinations instantly, and score latency down to the millisecond.
          </p>

          <div style={{ display: 'flex', gap: '1rem', justifyContent: 'center' }}>
            <a href="https://github.com/unforkopensource-org/decibench" target="_blank" rel="noopener noreferrer" style={{ background: '#fff', color: '#000', padding: '0.8rem 2rem', borderRadius: '8px', fontWeight: 600, fontSize: '1rem', transition: 'transform 0.2s' }} onMouseOver={(e) => e.currentTarget.style.transform = 'scale(1.05)'} onMouseOut={(e) => e.currentTarget.style.transform = 'scale(1)'}>
              Get Started
            </a>
            <a href="#features" style={{ background: 'rgba(255,255,255,0.05)', color: '#fff', border: '1px solid rgba(255,255,255,0.1)', padding: '0.8rem 2rem', borderRadius: '8px', fontWeight: 600, fontSize: '1rem', transition: 'background 0.2s' }} onMouseOver={(e) => e.currentTarget.style.background = 'rgba(255,255,255,0.1)'} onMouseOut={(e) => e.currentTarget.style.background = 'rgba(255,255,255,0.05)'}>
              View Documentation
            </a>
          </div>
        </motion.div>
      </section>

      {/* Metrics Banner */}
      <section style={{ padding: '4rem 2rem', background: 'rgba(0,0,0,0.4)', borderTop: '1px solid var(--glass-border)', borderBottom: '1px solid var(--glass-border)', display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '2rem', textAlign: 'center', zIndex: 10, position: 'relative' }}>
        <div>
          <div style={{ fontSize: '3rem', fontWeight: 700, color: 'var(--cyan)' }}>2,400+</div>
          <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: '0.9rem', marginTop: '0.5rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Test Scenarios</div>
        </div>
        <div>
          <div style={{ fontSize: '3rem', fontWeight: 700, color: 'var(--green)' }}>&lt;500ms</div>
          <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: '0.9rem', marginTop: '0.5rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>p50 Latency Target</div>
        </div>
        <div>
          <div style={{ fontSize: '3rem', fontWeight: 700, color: '#ff3366' }}>0</div>
          <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: '0.9rem', marginTop: '0.5rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Hallucinations Tolerated</div>
        </div>
      </section>

      {/* Features Grid */}
      <section id="features" style={{ padding: '8rem 2rem', maxWidth: '1200px', margin: '0 auto', zIndex: 10, position: 'relative' }}>
        <h2 style={{ fontSize: '2.5rem', fontWeight: 700, textAlign: 'center', marginBottom: '4rem', letterSpacing: '-0.02em' }}>Built for the Enterprise</h2>
        
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '2rem' }}>
          
          <div className="glass-card" style={{ padding: '2.5rem' }}>
            <Activity color="var(--cyan)" size={32} style={{ marginBottom: '1.5rem' }} />
            <h3 style={{ fontSize: '1.25rem', fontWeight: 600, marginBottom: '1rem' }}>Deterministic Matching</h3>
            <p style={{ color: 'rgba(255,255,255,0.6)', lineHeight: 1.6 }}>Fast, free, and rigid. Ensure exact keywords, disclaimers, or greetings are hit with sub-millisecond local string matching.</p>
          </div>

          <div className="glass-card" style={{ padding: '2.5rem' }}>
            <Cpu color="var(--green)" size={32} style={{ marginBottom: '1.5rem' }} />
            <h3 style={{ fontSize: '1.25rem', fontWeight: 600, marginBottom: '1rem' }}>Semantic LLM-as-a-Judge</h3>
            <p style={{ color: 'rgba(255,255,255,0.6)', lineHeight: 1.6 }}>Slower, nuanced testing using large language models to grade conversational accuracy, compliance, and hallucination rates.</p>
          </div>

          <div className="glass-card" style={{ padding: '2.5rem' }}>
            <ShieldAlert color="var(--purple)" size={32} style={{ marginBottom: '1.5rem' }} />
            <h3 style={{ fontSize: '1.25rem', fontWeight: 600, marginBottom: '1rem' }}>RAG-Augmented Adversarial</h3>
            <p style={{ color: 'rgba(255,255,255,0.6)', lineHeight: 1.6 }}>Upload your knowledge base and let Decibench auto-generate hostile test suites that actively try to break your agent's logic.</p>
          </div>

        </div>
      </section>
      
      {/* Footer */}
      <footer style={{ padding: '4rem 2rem', borderTop: '1px solid var(--glass-border)', textAlign: 'center', color: 'rgba(255,255,255,0.4)', fontSize: '0.9rem' }}>
        <p>Built with precision by developers, for developers.</p>
        <p style={{ marginTop: '0.5rem' }}>© 2026 Unfork Open Source.</p>
      </footer>

    </main>
  );
}
