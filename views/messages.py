"""Messages — inbox for the swap-network conversations with partner shops. DEMO preview."""

import streamlit as st

import cs_lib
import casa_report as C

cs_lib.page_title("Messages",
                  "Your conversations with partner shops in the swap network — arrange swaps, agree prices, "
                  "answer questions.", demo=True)

threads = st.session_state.get("threads", {})
if not threads:
    st.info("No messages yet. Open the **Swap network**, find a shop that wants your dead stock, and hit "
            "💬 Contact to start a conversation.")
    st.page_link("views/p_swap.py", label="Go to Swap network", icon="🔄")
    st.stop()

shops = list(threads.keys())
left, right = st.columns([1, 2.3])

with left:
    st.markdown("##### Conversations")
    st.radio("Conversations", shops, key="msg_sel", label_visibility="collapsed",
             format_func=lambda s: "💬 {}  ({})".format(s, len(threads[s])))

sel = st.session_state.get("msg_sel") or shops[0]

with right:
    st.markdown("##### {}".format(sel))
    with st.container(height=340):
        for m in threads[sel]:
            cls = "msg-you" if m["from"] == "you" else "msg-them"
            st.markdown("<div class='msg-row'><div class='{}'>{}</div></div>".format(
                cls, C.esc(m["text"])), unsafe_allow_html=True)

# chat input must be at page level (not inside a column)
reply = st.chat_input("Message {}…".format(sel))
if reply:
    cs_lib.add_message(sel, reply, "you")
    st.rerun()

st.caption("⚠️ Demo — messages are stored for this session only. In the live network these are real threads "
           "between shops, with swap offers and shipping built in.")
