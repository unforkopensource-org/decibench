<script setup lang="ts">
import { RouterLink, RouterView, useRoute } from 'vue-router'
import { computed } from 'vue'

const route = useRoute()

const isHome = computed(() => route.name === 'home')
const isActiveHome = computed(() => route.name === 'home')
const isActiveInbox = computed(() => route.name === 'inbox' || route.name === 'call' || route.name === 'evaluation')
const isActiveRuns = computed(() => route.name === 'runs' || route.name === 'run')
const isActiveRag = computed(() => route.name === 'rag' || route.name === 'rag_synthesize')
const mainClass = computed(() =>
  isHome.value ? 'flex-1' : 'section-shell flex-1 py-6',
)
</script>

<template>
  <div class="flex min-h-screen flex-col text-ink-900">
    <!-- ═══ NAVBAR ═══ -->
    <header
      class="sticky top-0 z-50 border-b backdrop-blur-xl"
      :class="isHome ? 'border-white/10 bg-ink-950/80 text-white' : 'border-ink-200/80 bg-white/90 text-ink-900'"
    >
      <div class="section-shell flex items-center justify-between gap-4 py-2.5">
        <!-- Logo + Nav -->
        <div class="flex items-center gap-5">
          <RouterLink to="/" class="group flex items-center gap-3">
            <div class="relative">
              <span
                class="grid h-9 w-9 place-items-center rounded-lg text-xs font-bold shadow-sm"
                :class="isHome ? 'bg-white/10 text-white ring-1 ring-white/10' : 'bg-ink-950 text-white'"
              >DB</span>
              <span class="absolute -top-0.5 -right-0.5 h-2 w-2 rounded-full bg-emerald-500 ring-2"
                :class="isHome ? 'ring-ink-950' : 'ring-white'"
              ></span>
            </div>
            <div class="hidden sm:block">
              <div class="text-sm font-bold leading-none tracking-tight">Decibench</div>
              <div class="mt-0.5 text-[10px] font-medium"
                :class="isHome ? 'text-white/50' : 'text-ink-400'"
              >Voice Agent QA</div>
            </div>
          </RouterLink>

          <nav class="flex items-center gap-0.5">
            <RouterLink
              to="/"
              class="flex items-center gap-1.5 rounded-md px-3 py-2 text-sm font-medium transition-all duration-150"
              :class="isActiveHome
                ? isHome ? 'bg-white text-ink-950' : 'bg-ink-950 text-white'
                : isHome ? 'text-white/70 hover:bg-white/10 hover:text-white' : 'text-ink-500 hover:bg-ink-50 hover:text-ink-900'"
            >
              <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" /></svg>
              <span class="hidden md:inline">Home</span>
            </RouterLink>
            <RouterLink
              to="/inbox"
              class="flex items-center gap-1.5 rounded-md px-3 py-2 text-sm font-medium transition-all duration-150"
              :class="isActiveInbox
                ? isHome ? 'bg-white text-ink-950' : 'bg-ink-950 text-white'
                : isHome ? 'text-white/70 hover:bg-white/10 hover:text-white' : 'text-ink-500 hover:bg-ink-50 hover:text-ink-900'"
            >
              <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" /></svg>
              <span class="hidden md:inline">Failure Inbox</span>
            </RouterLink>
            <RouterLink
              to="/runs"
              class="flex items-center gap-1.5 rounded-md px-3 py-2 text-sm font-medium transition-all duration-150"
              :class="isActiveRuns
                ? isHome ? 'bg-white text-ink-950' : 'bg-ink-950 text-white'
                : isHome ? 'text-white/70 hover:bg-white/10 hover:text-white' : 'text-ink-500 hover:bg-ink-50 hover:text-ink-900'"
            >
              <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" /></svg>
              <span class="hidden md:inline">Runs</span>
            </RouterLink>
            <RouterLink
              to="/test"
              class="flex items-center gap-1.5 rounded-md px-3 py-2 text-sm font-medium transition-all duration-150"
              :class="$route.name === 'test'
                ? isHome ? 'bg-white text-ink-950' : 'bg-ink-950 text-white'
                : isHome ? 'text-white/70 hover:bg-white/10 hover:text-white' : 'text-ink-500 hover:bg-ink-50 hover:text-ink-900'"
            >
              <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="6 4 20 12 6 20 6 4"/></svg>
              <span class="hidden md:inline">Test</span>
            </RouterLink>
            <RouterLink
              to="/rag"
              class="flex items-center gap-1.5 rounded-md px-3 py-2 text-sm font-medium transition-all duration-150"
              :class="isActiveRag
                ? isHome ? 'bg-white text-ink-950' : 'bg-ink-950 text-white'
                : isHome ? 'text-white/70 hover:bg-white/10 hover:text-white' : 'text-ink-500 hover:bg-ink-50 hover:text-ink-900'"
            >
              <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M4 4h12a4 4 0 014 4v12H8a4 4 0 01-4-4z"/><path d="M4 16a4 4 0 014-4h12"/></svg>
              <span class="hidden md:inline">Knowledge</span>
            </RouterLink>
          </nav>
        </div>

        <!-- Right -->
        <div class="flex items-center gap-2.5">
          <span class="rounded-md px-2 py-1 text-[11px] font-mono font-medium"
            :class="isHome ? 'bg-white/10 text-white/60 ring-1 ring-white/10' : 'bg-ink-50 text-ink-500 ring-1 ring-ink-200/60'"
          >v1.0.0</span>
          <a
            href="https://github.com/unforkopensource-org/decibench"
            target="_blank"
            rel="noreferrer"
            class="grid h-8 w-8 place-items-center rounded-md transition-colors"
            :class="isHome ? 'text-white/60 hover:text-white hover:bg-white/10' : 'text-ink-400 hover:text-ink-900 hover:bg-ink-50'"
          >
            <svg class="h-4 w-4" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/></svg>
          </a>
        </div>
      </div>
    </header>

    <main :class="mainClass">
      <RouterView />
    </main>

    <footer class="border-t border-ink-200/60 bg-white/80 py-4 backdrop-blur-sm">
      <div class="section-shell flex flex-col items-center justify-between gap-2 text-center text-xs text-ink-400 sm:flex-row">
        <div class="flex items-center gap-2">
          <span class="font-semibold text-ink-600">Decibench</span>
          <span class="text-ink-300">&middot;</span>
          <span>Open-source voice agent testing</span>
          <span class="text-ink-300">&middot;</span>
          <span class="font-mono text-ink-500">v0.1.0</span>
        </div>
        <code class="rounded bg-ink-50 px-2 py-0.5 text-[11px] text-ink-500">.decibench/decibench.sqlite</code>
      </div>
    </footer>
  </div>
</template>
