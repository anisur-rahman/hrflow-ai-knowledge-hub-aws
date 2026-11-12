import { createRouter, createWebHistory } from 'vue-router'
import { isAdmin } from '../services/session'

declare module 'vue-router' {
  interface RouteMeta { adminOnly?: boolean; title?: string }
}

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: () => (isAdmin.value ? '/dashboard' : '/chat') },
    { path: '/dashboard', component: () => import('../views/DashboardView.vue'), meta: { adminOnly: true, title: 'Dashboard' } },
    { path: '/documents', component: () => import('../views/DocumentsView.vue'), meta: { title: 'Documents' } },
    { path: '/chat', component: () => import('../views/ChatView.vue'), meta: { title: 'Policy assistant' } },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

router.beforeEach((to) => (to.meta.adminOnly && !isAdmin.value ? '/chat' : true))
router.afterEach((to) => { document.title = `${to.meta.title ?? 'Home'} · HRFlow AI Knowledge Hub` })

export default router
