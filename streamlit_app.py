"""
streamlit_app.py
─────────────────────────────────────────────────────────────────────────────
Streamlit POC interface for the SEO-Content-Engine.
Demonstrates the full loop with real-time feedback and visualizations.

Run with: streamlit run streamlit_app.py

Requires GROQ_API_KEY in .env or environment variables.
─────────────────────────────────────────────────────────────────────────────
"""

import os
import sys
import json
import streamlit as st
from pathlib import Path
from datetime import datetime

# Add repo root to path
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
import plotly.graph_objects as go
import plotly.express as px

from core.state import PipelineState
from core.knowledge_store import KnowledgeStore
from core.llm_client import LLMClient
from agents import research, generate, quality_gate, publish, evaluate, learn

# Load .env file
load_dotenv()

# ─────────────────────────────────────────────────────────────────────────────
# Page Config & Styling
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="SEO Content Engine | Premium",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for Premium Look
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap');
    
    :root {
        --primary: #10b981;
        --secondary: #3b82f6;
        --background: #0f172a;
        --text: #f8fafc;
        --card-bg: rgba(30, 41, 59, 0.7);
    }
    
    * { font-family: 'Outfit', sans-serif; }
    
    .main { background-color: var(--background); color: var(--text); }
    
    /* Glassmorphism Card */
    .stCard {
        background: var(--card-bg);
        backdrop-filter: blur(12px);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 16px;
        padding: 24px;
        margin-bottom: 20px;
        transition: transform 0.3s ease, box-shadow 0.3s ease;
    }
    
    .stCard:hover {
        transform: translateY(-5px);
        box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3);
    }
    
    .hero-title {
        font-size: 3.5rem;
        font-weight: 700;
        background: linear-gradient(135deg, #10b981, #3b82f6);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0;
    }
    
    .hero-subtitle {
        font-size: 1.25rem;
        color: #94a3b8;
        margin-bottom: 2rem;
    }
    
    /* Animation */
    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(20px); }
        to { opacity: 1; transform: translateY(0); }
    }
    
    .animate-in { animation: fadeIn 0.8s ease-out forwards; }
    
    /* Metrics */
    [data-testid="stMetricValue"] { font-size: 2rem; font-weight: 600; color: var(--primary) !important; }
    
    /* Buttons */
    .stButton > button {
        border-radius: 12px;
        background: linear-gradient(135deg, #10b981, #059669);
        color: white;
        border: none;
        padding: 0.6rem 2rem;
        font-weight: 600;
        transition: all 0.3s;
    }
    
    .stButton > button:hover {
        opacity: 0.9;
        transform: scale(1.02);
        box-shadow: 0 0 20px rgba(16, 185, 129, 0.4);
    }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Hero Section
# ─────────────────────────────────────────────────────────────────────────────

col_hero_1, col_hero_2 = st.columns([1.2, 1])

with col_hero_1:
    st.markdown('<div class="animate-in">', unsafe_allow_html=True)
    st.markdown('<h1 class="hero-title">SEO Content Engine</h1>', unsafe_allow_html=True)
    st.markdown('<p class="hero-subtitle">Autonomous, self-improving SEO orchestration powered by Groq.</p>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
    
with col_hero_2:
    hero_path = Path("assets/hero.png")
    if hero_path.exists():
        st.image(str(hero_path), use_container_width=True)

# ─────────────────────────────────────────────────────────────────────────────
# Session State
# ─────────────────────────────────────────────────────────────────────────────

if "pipeline_state" not in st.session_state:
    st.session_state.pipeline_state = None
if "store" not in st.session_state:
    st.session_state.store = None
if "config" not in st.session_state:
    st.session_state.config = None
if "loop_count" not in st.session_state:
    st.session_state.loop_count = 0


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar: Configuration & API Key
# ─────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("⚙️ Configuration")

    # API Key Input
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        api_key = st.text_input(
            "🔑 Groq API Key",
            value="",
            type="password",
            help="Get your free key from console.groq.com"
        )
        if api_key:
            os.environ["GROQ_API_KEY"] = api_key
    else:
        st.success("✓ API Key loaded from .env")

    st.divider()

    # Client Configuration
    st.subheader("📰 Client Config")

    client_name = st.text_input(
        "Blog Name",
        value="TechStartup Blog",
        help="The name of your blog/client"
    )

    domain = st.text_input(
        "Domain",
        value="techstartup.io",
        help="Your blog domain"
    )

    st.subheader("🎯 Topic Settings")

    niche = st.text_area(
        "Domain Niche",
        value="AI tools and automation for startups and SMBs",
        height=60,
        help="What your blog is about"
    )

    tone = st.selectbox(
        "Writing Tone",
        options=[
            "practical, direct, jargon-light",
            "technical, in-depth, academic",
            "conversational, friendly, accessible",
            "authoritative, data-led, professional"
        ],
        index=0
    )

    audience = st.text_area(
        "Target Audience",
        value="non-technical founders and startup operators aged 28–45",
        height=60
    )

    seed_keywords = st.text_area(
        "Seed Keywords (one per line)",
        value="AI productivity tools\nstartup automation\nmachine learning for small business\nno-code AI\nChatGPT for business",
        height=100,
        help="Your main topic areas"
    )

    st.divider()

    st.subheader("📊 Quality Gate Thresholds")
    col1, col2 = st.columns(2)
    with col1:
        min_score = st.slider("Min Score", 0.5, 1.0, 0.65, step=0.05)
    with col2:
        min_wc = st.number_input("Min Words", 300, 2000, 600)

    st.divider()

    st.subheader("📁 Knowledge Store")
    store_path = "store/knowledge.json"
    if st.button("🔄 Reset Store", help="Delete all historical data"):
        store_file = Path(store_path)
        if store_file.exists():
            store_file.unlink()
            st.success("✓ Store reset")
            st.rerun()

    # Build config dict
    config = {
        "client": {
            "name": client_name,
            "domain": domain,
            "base_url": f"https://{domain}/blog"
        },
        "topic": {
            "seed_keywords": [k.strip() for k in seed_keywords.split("\n") if k.strip()],
            "domain_niche": niche,
            "target_audience": audience,
            "tone": tone,
            "avoid_topics": []
        },
        "publish": {
            "destination": "local_markdown",
            "output_dir": "output/posts"
        },
        "quality_gate": {
            "min_word_count": min_wc,
            "max_word_count": 2500,
            "min_score": min_score,
            "required_sections": ["Introduction", "Conclusion"],
            "min_keyword_density": 0.005,
            "max_keyword_density": 0.030
        },
        "llm": {
            "provider": "groq",
            "model": "llama-3.3-70b-versatile",
            "temperature": 0.7,
            "max_tokens": 3000
        }
    }

    st.session_state.config = config


# ─────────────────────────────────────────────────────────────────────────────
# Status Bar
# ─────────────────────────────────────────────────────────────────────────────

st.markdown(f"""
<div class="stCard" style="padding: 10px 24px; margin-bottom: 30px; display: flex; justify-content: space-between; align-items: center;">
    <div style="font-size: 1.1rem; font-weight: 600; color: #10b981;">🚀 SYSTEM ONLINE</div>
    <div style="font-size: 1rem; color: #94a3b8;">Current Loop: <span style="color: white; font-weight: 600;">#{st.session_state.loop_count + 1}</span></div>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Tabs: Dashboard, Run Loop, View Results, Analytics
# ─────────────────────────────────────────────────────────────────────────────

tab_run, tab_dashboard, tab_results, tab_analytics = st.tabs([
    "🚀 Run Loop",
    "📊 Dashboard",
    "📄 Latest Results",
    "📈 Analytics"
])


with tab_run:
    st.header("Execute SEO Content Loop")

    col1, col2 = st.columns(2)

    with col1:
        dry_run = st.checkbox(
            "🏃 Dry Run Mode",
            value=False,
            help="Run through to Quality Gate only, don't publish"
        )

    with col2:
        if not os.getenv("GROQ_API_KEY"):
            st.error("⚠️ Groq API Key required. Enter it in the sidebar.")
        else:
            st.success("✓ API Key ready")

    if st.button("▶️ Start Loop", key="run_loop", type="primary", use_container_width=True):
        if not os.getenv("GROQ_API_KEY"):
            st.error("❌ Groq API Key not set. Add it in the sidebar.")
        else:
            try:
                st.session_state.store = KnowledgeStore("store/knowledge.json")
                st.session_state.loop_count = st.session_state.store.get_loop_count()

                # Create placeholder for progress
                progress_placeholder = st.empty()
                status_placeholder = st.empty()

                # Stage 1: Research
                with progress_placeholder.container():
                    st.info("🔍 Stage 1/5: Researching topic opportunities...")
                state = PipelineState(config=st.session_state.config)
                state = research.run(state, st.session_state.store, LLMClient(st.session_state.config))

                if state.aborted_at:
                    st.error(f"❌ Aborted at {state.aborted_at}")
                    for err in state.errors:
                        st.error(f"  • {err}")
                else:
                    with progress_placeholder.container():
                        st.success("✓ Research complete")
                    with status_placeholder.container():
                        st.write(f"**Topic:** {state.research.chosen_topic}")
                        st.write(f"**Keyword:** {state.research.primary_keyword}")
                        st.write(f"**Angle:** {state.research.suggested_angle}")

                    # Stage 2: Generate
                    with progress_placeholder.container():
                        st.info("✍️ Stage 2/5: Generating SEO blog post...")
                    state = generate.run(state, st.session_state.store, LLMClient(st.session_state.config))

                    if state.aborted_at:
                        st.error(f"❌ Aborted at {state.aborted_at}")
                    else:
                        with progress_placeholder.container():
                            st.success("✓ Article generated")
                        with status_placeholder.container():
                            st.metric("Word Count", state.generation.word_count)
                            st.metric("Keyword Density", f"{state.generation.keyword_density:.2%}")

                        # Stage 2b: Quality Gate
                        with progress_placeholder.container():
                            st.info("🚪 Stage 2b/5: Running quality gate...")
                        state = quality_gate.run(state)

                        if state.quality_gate.passed:
                            with progress_placeholder.container():
                                st.success(f"✓ Quality gate PASSED (score: {state.quality_gate.score:.2f})")
                            with status_placeholder.container():
                                st.metric("Quality Score", f"{state.quality_gate.score:.3f}", delta=f"{(state.quality_gate.score - 0.65):.3f}")

                            if not dry_run:
                                # Stage 3: Publish
                                with progress_placeholder.container():
                                    st.info("📤 Stage 3/5: Publishing article...")
                                state = publish.run(state)

                                if state.aborted_at:
                                    st.error(f"❌ Aborted at {state.aborted_at}")
                                else:
                                    with progress_placeholder.container():
                                        st.success("✓ Article published")
                                    with status_placeholder.container():
                                        st.write(f"**File:** {Path(state.publish.destination_path).name}")

                                    # Stage 4: Evaluate
                                    with progress_placeholder.container():
                                        st.info("📊 Stage 4/5: Evaluating content quality...")
                                    state = evaluate.run(state, LLMClient(st.session_state.config))

                                    if state.aborted_at:
                                        st.error(f"❌ Aborted at {state.aborted_at}")
                                    else:
                                        with progress_placeholder.container():
                                            st.success("✓ Evaluation complete")
                                        with status_placeholder.container():
                                            col1, col2, col3 = st.columns(3)
                                            with col1:
                                                st.metric("Overall Score", f"{state.evaluation.overall_score:.2f}")
                                            with col2:
                                                st.metric("Semantic", f"{state.evaluation.semantic_coverage_score:.2f}")
                                            with col3:
                                                st.metric("Readability", f"{state.evaluation.readability_score:.2f}")

                                        # Stage 5: Learn
                                        with progress_placeholder.container():
                                            st.info("🧠 Stage 5/5: Learning and updating knowledge base...")
                                        state = learn.run(state, st.session_state.store)

                                        with progress_placeholder.container():
                                            st.success("✓ Loop complete!")
                                        with status_placeholder.container():
                                            st.balloons()
                                            st.success(f"**Article published & evaluated. Knowledge store updated.**")
                            else:
                                with progress_placeholder.container():
                                    st.info("🏁 Dry run complete (stopped before publish)")
                        else:
                            with progress_placeholder.container():
                                st.error(f"✗ Quality gate FAILED (score: {state.quality_gate.score:.2f})")
                            with status_placeholder.container():
                                st.warning("**Failures:**")
                                for fail in state.quality_gate.failures:
                                    st.write(f"  ❌ {fail}")
                                if state.quality_gate.warnings:
                                    st.warning("**Warnings:**")
                                    for warn in state.quality_gate.warnings:
                                        st.write(f"  ⚠️ {warn}")

                        st.session_state.pipeline_state = state

            except Exception as e:
                st.error(f"❌ Error: {str(e)}")
                import traceback
                st.code(traceback.format_exc())


with tab_dashboard:
    st.markdown("## 📊 Knowledge Store Dashboard")

    if st.session_state.store is None:
        st.session_state.store = KnowledgeStore("store/knowledge.json")

    store = st.session_state.store

    # Top metrics
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("📚 Loops Completed", store.get_loop_count())
    with col2:
        st.metric("📝 Topics Covered", len(store.get_covered_topics()))
    with col3:
        avg_score = store.get_avg_quality_score()
        st.metric("⭐ Avg Quality", f"{avg_score:.3f}" if avg_score else "—")
    with col4:
        best = store.get_quality_history()
        best_score = max([h["score"] for h in best], default=0)
        st.metric("🏆 Best Score", f"{best_score:.3f}" if best_score else "—")

    st.divider()

    # Topics covered
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### 📚 Topics Covered")
        topics = store.get_covered_topics()
        if topics:
            for i, topic in enumerate(topics, 1):
                st.write(f"{i}. {topic.title()}")
        else:
            st.info("No topics covered yet. Run a loop to get started!")

    with col2:
        st.markdown("### 🎯 Preferred Angles")
        angles = store.get_preferred_angles()
        if angles:
            for angle in angles[:5]:
                st.caption(f"✓ {angle}")
        else:
            st.info("Angles will appear after first evaluation")

    st.divider()

    # Quality history
    st.subheader("Quality Score History")
    history = store.get_quality_history()
    if history:
        scores = [h["score"] for h in history]
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            y=scores,
            mode='lines+markers',
            name='Quality Score',
            line=dict(color='#09ab3b', width=3),
            marker=dict(size=8)
        ))
        fig.add_hline(y=0.65, line_dash="dash", line_color="#ff9500", annotation_text="Min threshold")
        fig.update_layout(
            title="Quality Score Progression",
            xaxis_title="Loop #",
            yaxis_title="Score",
            height=400,
            hovermode='x unified'
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Run loops to see quality progression")

    st.divider()

    # Learned patterns
    patterns = store.get_high_performing_structures()
    if patterns:
        st.markdown("### 📌 High-Performing Structures")
        for pattern in patterns[:3]:
            with st.expander(f"📌 {pattern[:60]}..."):
                st.code(pattern)
    else:
        st.info("Structures will be learned as loops complete")


with tab_results:
    st.markdown("## 📄 Latest Loop Results")

    if st.session_state.pipeline_state is None:
        st.info("Run a loop to see results here")
    else:
        state = st.session_state.pipeline_state

        # Research phase
        if state.research:
            with st.expander("🔍 Research Output", expanded=True):
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**Topic:** {state.research.chosen_topic}")
                    st.write(f"**Primary Keyword:** {state.research.primary_keyword}")
                with col2:
                    st.write(f"**Suggested Angle:** {state.research.suggested_angle}")
                st.write(f"**Why:** {state.research.content_gap_reason}")

        # Generation phase
        if state.generation:
            with st.expander("✍️ Generated Article", expanded=False):
                st.write(f"**Title:** {state.generation.title}")
                st.write(f"**Meta Description:** {state.generation.meta_description}")
                st.write(f"**Word Count:** {state.generation.word_count}")
                st.write(f"**Keyword Density:** {state.generation.keyword_density:.2%}")
                st.write(f"**Sections:** {', '.join(state.generation.sections)}")
                st.write("---")
                st.markdown(state.generation.body_markdown)

        # Quality Gate
        if state.quality_gate:
            with st.expander("🚪 Quality Gate", expanded=True):
                if state.quality_gate.passed:
                    st.success(f"✓ PASSED (Score: {state.quality_gate.score:.3f})")
                else:
                    st.error(f"✗ FAILED (Score: {state.quality_gate.score:.3f})")
                if state.quality_gate.failures:
                    st.warning("**Failures:**")
                    for fail in state.quality_gate.failures:
                        st.write(f"  • {fail}")
                if state.quality_gate.warnings:
                    st.info("**Warnings:**")
                    for warn in state.quality_gate.warnings:
                        st.write(f"  • {warn}")

        # Evaluation
        if state.evaluation:
            with st.expander("📊 Evaluation Scores", expanded=True):
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Overall", f"{state.evaluation.overall_score:.2f}")
                with col2:
                    st.metric("Semantic", f"{state.evaluation.semantic_coverage_score:.2f}")
                with col3:
                    st.metric("Keyword", f"{state.evaluation.keyword_score:.2f}")

                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Readability", f"{state.evaluation.readability_score:.2f}")
                with col2:
                    st.metric("Structure", f"{state.evaluation.structural_score:.2f}")
                with col3:
                    st.metric("Linking", f"{state.evaluation.internal_linking_score:.2f}")

                if state.evaluation.strengths:
                    st.success("**Strengths:**")
                    for s in state.evaluation.strengths:
                        st.write(f"  ✓ {s}")

                if state.evaluation.improvements:
                    st.warning("**Improvements:**")
                    for imp in state.evaluation.improvements:
                        st.write(f"  → {imp}")


with tab_analytics:
    st.markdown("## 📈 System Analytics")

    if st.session_state.store is None:
        st.session_state.store = KnowledgeStore("store/knowledge.json")

    store = st.session_state.store

    # Quality distribution
    history = store.get_quality_history()
    if history:
        col1, col2 = st.columns(2)

        with col1:
            scores = [h["score"] for h in history]
            fig = px.histogram(
                x=scores,
                nbins=10,
                title="Quality Score Distribution",
                labels={"x": "Score", "count": "Frequency"},
                color_discrete_sequence=["#09ab3b"]
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            stats = {
                "Mean": sum(scores) / len(scores),
                "Median": sorted(scores)[len(scores)//2],
                "Min": min(scores),
                "Max": max(scores),
                "StdDev": (sum((x - sum(scores)/len(scores))**2 for x in scores) / len(scores))**0.5
            }
            for stat, value in stats.items():
                st.metric(stat, f"{value:.3f}")

        st.divider()

        # Trends
        st.markdown("### 📊 Score Trends")
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            y=scores,
            mode='lines+markers',
            name='Score',
            line=dict(color='#1f77b4', width=2),
            fill='tozeroy',
            fillcolor='rgba(31, 119, 180, 0.2)'
        ))

        # Add moving average
        if len(scores) > 1:
            ma = []
            window = min(3, len(scores))
            for i in range(len(scores)):
                if i < window:
                    ma.append(sum(scores[:i+1]) / (i+1))
                else:
                    ma.append(sum(scores[i-window+1:i+1]) / window)
            fig.add_trace(go.Scatter(
                y=ma,
                mode='lines',
                name=f'{window}-loop MA',
                line=dict(color='#ff7f0e', width=2, dash='dash')
            ))

        fig.update_layout(
            title="Quality Score Trends with Moving Average",
            xaxis_title="Loop #",
            yaxis_title="Score",
            height=500,
            hovermode='x unified'
        )
        st.plotly_chart(fig, use_container_width=True)

    else:
        st.info("Run multiple loops to see analytics")

    st.divider()

    # Keyword usage
    keyword_usage = store.get_keyword_usage()
    if keyword_usage:
        st.markdown("### 🔑 Keyword Utilization")
        keywords = sorted(keyword_usage.items(), key=lambda x: x[1], reverse=True)
        fig = px.bar(
            x=[k[0] for k in keywords],
            y=[k[1] for k in keywords],
            title="Keywords Used by Frequency",
            labels={"x": "Keyword", "y": "Times Used"},
            color_discrete_sequence=["#09ab3b"]
        )
        fig.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # System Summary
    st.markdown("### 📋 System Summary")
    st.info(store.summary())
