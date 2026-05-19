import { createRouter, createWebHashHistory } from 'vue-router';
import Overview from '../views/Overview.vue';
import Plans from '../views/Plans.vue';

// Hash mode keeps deployment trivial: FastAPI just serves index.html at /,
// no rewrite rules needed.
export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', redirect: '/overview' },
    { path: '/overview', name: 'overview', component: Overview, meta: { title: '总览' } },
    { path: '/plans', name: 'plans', component: Plans, meta: { title: '持股计划' } },
  ],
});
