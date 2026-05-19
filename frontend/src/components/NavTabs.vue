<script setup lang="ts">
import { useRoute } from 'vue-router';
const route = useRoute();
</script>

<template>
  <nav class="flex border-b border-gray-200 bg-white">
    <RouterLink
      to="/overview"
      class="px-5 py-3 text-sm font-medium border-b-2 transition-colors"
      :class="route.name === 'overview'
        ? 'border-accent text-accent'
        : 'border-transparent text-gray-500 hover:text-gray-800'"
    >总览</RouterLink>
    <RouterLink
      to="/plans"
      class="px-5 py-3 text-sm font-medium border-b-2 transition-colors"
      :class="route.name === 'plans'
        ? 'border-accent text-accent'
        : 'border-transparent text-gray-500 hover:text-gray-800'"
    >持股计划</RouterLink>
  </nav>
</template>
