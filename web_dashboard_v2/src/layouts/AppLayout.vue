<template>
  <div class="app-layout">
    <NavBar />
    <div class="main-container">
      <SideBar />
      <main class="content-area">
        <router-view />
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import NavBar from '@/components/layout/NavBar.vue';
import SideBar from '@/components/layout/SideBar.vue';
</script>

<style scoped lang="scss">
.app-layout {
  display: flex;
  flex-direction: column;
  height: 100vh;
}

.main-container {
  display: flex;
  flex: 1;
  overflow: hidden;
}

.content-area {
  flex: 1;
  padding: $spacing-md;
  overflow: auto;
  background-color: var(--bg-secondary);
}
</style>
