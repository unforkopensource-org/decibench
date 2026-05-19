import { createRouter, createWebHashHistory } from 'vue-router'

import CallDetail from './views/CallDetail.vue'
import EvaluationDetail from './views/EvaluationDetail.vue'
import FailureInbox from './views/FailureInbox.vue'
import HomeView from './views/HomeView.vue'
import RunDetail from './views/RunDetail.vue'
import RunsList from './views/RunsList.vue'
import TestAgent from './views/TestAgent.vue'
import RagCorpus from './views/RagCorpus.vue'
import RagSynthesize from './views/RagSynthesize.vue'

// We use hash routing so the dashboard can be served from a single static
// `index.html` by FastAPI without needing a server-side rewrite rule.
export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', name: 'home', component: HomeView },
    { path: '/inbox', name: 'inbox', component: FailureInbox },
    { path: '/calls/:callId', name: 'call', component: CallDetail, props: true },
    {
      path: '/evaluations/:evaluationId',
      name: 'evaluation',
      component: EvaluationDetail,
      props: true,
    },
    { path: '/runs', name: 'runs', component: RunsList },
    { path: '/runs/:runId', name: 'run', component: RunDetail, props: true },
    { path: '/test', name: 'test', component: TestAgent },
    { path: '/rag', name: 'rag', component: RagCorpus },
    { path: '/rag/synthesize', name: 'rag_synthesize', component: RagSynthesize },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})
