import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './components/App.vue'

createApp(App).use(createPinia()).mount('#app')
