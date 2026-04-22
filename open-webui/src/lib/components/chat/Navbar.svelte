<script lang="ts">
	import { getContext } from 'svelte';
	import {
		chatId
	} from '$lib/stores';
	import { get } from 'svelte/store';
	import { showSidebar } from '$lib/stores';
	import { onMount } from 'svelte';
	import ShareChatModal from '../chat/ShareChatModal.svelte';
	import Tooltip from '../common/Tooltip.svelte';

	const i18n = getContext('i18n');
	
	export let initNewChat: Function;
	export let selectedModels;
	export let params: { think?: boolean | string | null; [key: string]: any } = {};
	// let showShareChatModal = false;
	// onMount(() => {
	// 	selectedModels.set(['rag-qwen']);
	// });

	const toggleThinking = () => {
		const current = params?.think ?? null;
		const next = current === true ? false : true;

		// bind된 parent(Chat.svelte) params까지 반영되도록 재할당
		params = {
			...params,
			think: next
		};
	};
</script>
<!-- <ShareChatModal bind:show={showShareChatModal} chatId={$chatId} /> -->

<button
	id="new-chat-button"
	class="hidden"
	on:click={() => {
		initNewChat();
	}}
	aria-label="New Chat"
/>

<nav class="sidebar {$showSidebar ? 'show-sidebar' : ''}">
	<div class="sidebar-main">

		<!-- TOP -->
		<div class="sidebar-section top">
			<div class="ai-title">
				<span class="title-icon">🎓</span>
				<span>감리교신학대학교 AI</span>
			</div>

			<div class="badge">감리교신학대학교 AI</div>
		</div>

		<!-- MIDDLE -->
		<div class="sidebar-section middle">
			<div class="engine-box">

				<div class="engine-title">AI ENGINE</div>

				<div class="engine-meta">
					다양한 질의에 즉시<br/>응답하는 AI 플랫폼입니다.
				</div>

				<div class="engine-meta sub">
					KOTECH의 <br/> RAG 서버 기술을 통해<br/>
					정확성과 신뢰성을 동시에 확보한 <br/>AI 서비스를 제공합니다.
				</div>

			</div>
		</div>

	</div>

	<!-- BOTTOM -->
	<div class="sidebar-section bottom">
		<div class="bottom-content">
			<Tooltip content={$i18n.t('Thinking')}>
				<button
					class="think-toggle"
					on:click={toggleThinking}
					aria-label="Thinking Toggle"
				>
					{params?.think === true ? 'TH ON' : 'TH OFF'}
				</button>
			</Tooltip>
			<div class="data-source">
				성경 기반
			</div>

			<p class="collab-text">
				<span class="exaone">LLM</span> 기반 지능형 AI<br/>
				<span class="sub">Powered by KOTECH RAG Engine</span>
			</p>
		</div>
	</div>
</nav>

<style>

/* =========================
   SIDEBAR 기본 구조
========================= */
.sidebar {
    width: 260px;
    height: 100vh;
    position: fixed;
    left: 0;
    top: 0;
    background: #f9fafb;
    border-right: 1px solid #e5e7eb;

    /* 좌우 패딩을 동일하게 맞추어 내부 콘텐츠가 쏠리지 않게 합니다 */
    padding: 40px 0; 
    
    display: flex;
    flex-direction: column;
    align-items: center; /* 가로축 중앙 정렬 추가 */
    z-index: 50;
    transition: transform 0.3s ease;
}

/* =========================
   본문 밀기 (핵심 ⭐)
========================= */
:global(body) {
	transition: padding-left 0.3s ease;
}

@media (min-width: 1025px) {
	:global(body) {
		padding-left: 260px;
	}
}


/* =========================
   모바일
========================= */
@media (max-width: 1024px) {
	.sidebar {
		transform: translateX(-100%);
		box-shadow: 5px 0 15px rgba(0,0,0,0.1);
	}

	:global(.show-sidebar) .sidebar {
		transform: translateX(0);
	}

	:global(body) {
		padding-left: 0;
	}
}

/* =========================
   중앙 정렬 핵심
========================= */
.sidebar-main {
    width: 100%; /* 부모 너비를 꽉 채워야 내부 align-items가 작동합니다 */
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 60px;
	margin-top: 40%;
	overflow-y: auto;
}

/* =========================
   TOP
========================= */
.sidebar-section.top {
	display: flex;
	flex-direction: column;
	align-items: center;
}

.ai-title {
	display: flex;
	align-items: center;
	justify-content: center;
	gap: 6px;

	font-size: 19px;
	font-weight: 700;
	color: #111827;

	margin-bottom: 30px;
}

.title-icon {
	font-size: 17px;
	opacity: 0.7;
}

.badge {
	display: block;
	margin: 0 auto;

	font-size: 10px;
	font-weight: 600;

	color: #e6007e;
	background: rgba(230,0,126,0.08);

	padding: 6px 14px;
	border-radius: 999px;

	width: fit-content;
}

/* =========================
   MIDDLE
========================= */
.sidebar-section.middle {
	display: flex;
	flex-direction: column;
	align-items: center;
}

.sidebar-section.middle::before {
	content: "";
	width: 40px;
	height: 1px;
	background: rgba(0,0,0,0.06);
	margin-bottom: 18px;
}

/* ENGINE BOX */
.engine-box {
	display: flex;
	flex-direction: column;
	align-items: center;

	gap: 16px;

	padding: 20px 16px;
	border-radius: 16px;

	background: rgba(255,255,255,0.6);
	backdrop-filter: blur(10px);

	border: 1px solid rgba(0,0,0,0.04);

	box-shadow: 0 4px 14px rgba(0,0,0,0.04);
}

.engine-title {
	font-size: 9px;
	font-weight: 700;
	color: #9ca3af;
	letter-spacing: 1.4px;
}

.engine-logos img {
	width: 110px;
	filter: grayscale(20%) brightness(0.95);
	opacity: 0.9;
	transition: all 0.2s ease;
}

.engine-box:hover img {
	filter: none;
	opacity: 1;
}

.engine-meta {
    font-size: 11px;
    color: #6b7280;
    text-align: center;
    line-height: 1.6;
    max-width: 210px; /* 180px에서 조금 늘림 */
}

.engine-meta.sub {
	font-size: 10px;
	opacity: 0.85;
}

/* =========================
   BOTTOM
========================= */
.sidebar-section.bottom {
    position: absolute;
    bottom: 123px;
    left: 0;    /* 왼쪽 끝 고정 */
    right: 0;   /* 오른쪽 끝 고정 */
    width: 100%; 
    display: flex;
    justify-content: center; /* 내부 콘텐츠를 가로 중앙으로 */
}

.bottom-content {
	display: flex;
	flex-direction: column;
	align-items: center;
	gap: 10px;
}

.data-source {
	font-size: 11px;
	color: #6b7280;
	text-align: center;
	line-height: 1.5;
}

.collab-text {
	font-size: 12px;
	font-weight: 600;
	text-align: center;
	line-height: 1.6;
}

.exaone {
	color: #d946ef;
	font-weight: 600;
}

.collab-text .sub {
	display: block;
	font-size: 11px;
	color: #6b7280;
	margin-top: 6px;
}

.think-toggle {
	display: inline-flex;
	align-items: center;
	justify-content: center;
	padding: 6px 14px;
	border-radius: 999px;
	font-size: 11px;
	font-weight: 600;
	color: #6b7280;
	background: rgba(0,0,0,0.04);
	border: 1px solid rgba(0,0,0,0.06);
	cursor: pointer;
	transition: all 0.2s ease;
}

.think-toggle:hover {
	background: rgba(0,0,0,0.08);
	color: #111827;
}

</style>







