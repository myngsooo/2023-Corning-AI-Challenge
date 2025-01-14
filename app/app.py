import os
import langchain
import streamlit as st

from collections import defaultdict
from urllib.error import URLError
from dotenv import load_dotenv
load_dotenv()

if os.environ.get("QNA_DEBUG") == "true":
    langchain.debug = True
os.environ["CUDA_DEVICE_ORDER"]="PCI_BUS_ID"  # Arrange GPU devices starting from 0
os.environ["CUDA_VISIBLE_DEVICES"]= "0"
from qna.llm import make_qna_chain, get_llm
# from qna.db import get_cache, get_vectorstore
from qna.db import get_vectorstore
from qna.prompt import basic_prompt
from qna.data import get_arxiv_docs
# from qna.constants import REDIS_URL

# @st.cache_resource
# def fetch_llm_cache():
#     return get_cache()

@st.cache_resource
def create_arxiv_index(topic_query, _num_papers, _prompt):
    arxiv_documents = get_arxiv_docs(topic_query, _num_papers)
    arxiv_db = get_vectorstore(arxiv_documents)
    st.session_state['arxiv_db'] = arxiv_db
    len_doc = []
    for i in range(len(arxiv_documents)):
        len_doc.append(arxiv_documents[i].metadata['source'])
    # print("len!!!!!!!!!!", len(len_doc))
        
    st.session_state['doc_path'] = len_doc
        # print("!!!!!!!!!",arxiv_documents[0].metadata['source'])
    # st.session_state['doc_path'] = arxiv_documents[0].metadata['source']
    return arxiv_db

def is_updated(topic):
    return (
        topic != st.session_state['previous_topic']
    )

def reset_app():
    st.session_state['previous_topic'] = ""
    st.session_state['arxiv_topic'] = ""
    st.session_state['arxiv_query'] = ""
    st.session_state['messages'].clear()

    arxiv_db = st.session_state['arxiv_db']
    # if arxiv_db is not None:
        # clear_cache()
        # arxiv_db.drop_index(arxiv_db.index_name, delete_documents=True, redis_url=REDIS_URL)
        # st.session_state['arxiv_db'] = None

def clear_cache():
    if not st.session_state["llm"]:
        st.warning("Could not find llm to clear cache of")
    llm = st.session_state["llm"]
    llm_string = llm._get_llm_string()
    langchain.llm_cache.clear(llm_string=llm_string)
    
try:
    # langchain.llm_cache = fetch_llm_cache()
    prompt = basic_prompt()

    # Defining default values
    default_question = ""
    default_answer = ""
    defaults = {
        "response": {
            "choices" :[{
                "text" : default_answer
            }]
        },
        # "question": default_question,
        "context": [],
        "chain": None,
        "previous_topic": "",
        "arxiv_topic": "",
        "arxiv_query": "",
        "arxiv_db": None,
        "llm": None,
        "messages": [],
    }

    # Checking if keys exist in session state, if not, initializing them
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

    with st.sidebar:
        st.write("## LLM Settings")
        ##st.write("### Prompt") TODO make possible to change prompt
        st.write("Change these before you run the app!")
        st.slider("Number of Tokens", 100, 8000, 400, key="max_tokens")

        st.write("## Retrieval Settings")
        st.write("Feel free to change these anytime")
        st.slider("Number of Context Documents", 2, 20, 2, key="num_context_docs")
        st.slider("Distance Threshold", .1, .9, .5, key="distance_threshold", step=.1)

        st.write("## App Settings")
        st.button("Clear Chat", key="clear_chat", on_click=lambda: st.session_state['messages'].clear())
        st.button("Clear Cache", key="clear_cache", on_click=clear_cache)
        st.button("New Conversation", key="reset", on_click=reset_app)

    col1, col2 = st.columns(2)
    with col1:
        st.title("CorningAI")
        st.write("**Put in a topic area and a question within that area to get an answer!**")
        # topic = st.text_input("Topic Area", key="arxiv_topic")
        # papers = st.number_input("Number of Papers", key="num_papers", value=10, min_value=1, max_value=50, step=2)
    with col2:
        st.image("./assets/logo-glass-bg.png")

    # if st.button("Chat!"):
    #     #if is_updated(topic):
    #     # st.session_state['previous_topic'] = topic
    #     with st.spinner("Loading information from Arxiv to answer your question..."):
    #         # create_arxiv_index(st.session_state['arxiv_topic'], st.session_state['num_papers'], prompt)
    #         st.session_state["find_doc"] = False
    
    # if st.button("Paper_list"):
    #     # if is_updated(topic):
    #     # st.session_state['previous_topic'] = topic
    #     with st.spinner("Loading information from Arxiv to answer your question..."):
    #         # create_arxiv_index(st.session_state['arxiv_topic'], st.session_state['num_papers'], prompt)
    #         st.session_state["find_doc"] = True

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    st.session_state['find_doc'] = False
    if query := st.chat_input("What do you want to know about this topic?"):
        st.session_state.messages.append({"role": "user", "content": query})
        with st.chat_message("user"):
            st.markdown(query)
        topic = query
        st.session_state['previous_topic'] = topic
        papers = st.number_input("Number of Papers", key="num_papers", value=1, min_value=1, max_value=50, step=2)
        create_arxiv_index(st.session_state['arxiv_topic'], st.session_state['num_papers'], prompt)
        arxiv_db = st.session_state['arxiv_db']
        if st.session_state["llm"] is None:
            tokens = st.session_state["max_tokens"]
            st.session_state["llm"] = get_llm(max_tokens=tokens)
        try:
            chain = make_qna_chain(
                st.session_state["llm"],
                arxiv_db,
                prompt=prompt,
                k=st.session_state['num_context_docs'],
                search_type="similarity_distance_threshold",
                distance_threshold=st.session_state["distance_threshold"]
            )
            st.session_state['chain'] = chain
        except AttributeError:
            st.info("Please enter a topic area")
            st.stop()
        if st.session_state['find_doc'] == False:
            with st.chat_message("assistant", avatar="./assets/logo-glass-bg.png"):
                message_placeholder = st.empty()
                st.session_state['context'], st.session_state['response'] = [], ""
                chain = st.session_state['chain']
                try:
                    # result = chain({"question": query, 'input_documents': arxiv_db})
                    multi_turn_dialgoues = [f"Speaker 1: {message['content']}" if  idx%2==0 else f"Speaker 2: {message['content']}" for idx, message in enumerate(st.session_state.messages)]
                    if len(multi_turn_dialgoues)%2==0: 
                       last_dialogues = "\nSpeaker 1: ###\n"
                    else:
                        last_dialogues = "\nSpeaker 2: ###\n"
                    dialogues  = '\n'.join(multi_turn_dialgoues).strip('\n') + last_dialogues
                    result = chain({"query": dialogues})
                    print('result:', result)
                    
                    # single-turn
                    # result = chain({"query": dialogues})
                except IndexError:
                    st.info("해당 유사도 이상의 다큐먼트가 존재하지 않습니다.")
                    st.stop()
                st.markdown(result["result"])
                # st.markdown(result)
                st.session_state['context'], st.session_state['response'] = result['source_documents'], result['result']
                # st.session_state['context'], st.session_state['response'] = result, result
                if st.session_state['context']:
                    with st.expander("Context"):
                        context = defaultdict(list)
                        for doc in st.session_state['context']:
                            context[doc.metadata['source']].append(doc)
                        for i, doc_tuple in enumerate(context.items(), 1):
                            source, doc_list = doc_tuple[0], doc_tuple[1]
                            st.write(f"{i}. **{source}**")
                            for context_num, doc in enumerate(doc_list, 1):
                                st.write(f"{i}. - **Context {context_num}**: {doc.page_content}")

                st.session_state.messages.append({"role": "assistant", "content": st.session_state['response']})
        else:
            message_placeholder = st.empty()
            st.session_state['context'], st.session_state['response'] = [], ""
            chain = st.session_state['chain']
            result = chain({"query": query})
            st.session_state['context'], st.session_state['response'] = result['source_documents'], result['result']
            if st.session_state['context']:
                    with st.expander("Context"):
                        context = defaultdict(list)
                        for doc in st.session_state['context']:
                            context[doc.metadata['source']].append(doc)
                        for i, doc_tuple in enumerate(context.items(), 1):
                            source, doc_list = doc_tuple[0], doc_tuple[1]
                            for i in range(len(doc_list)):
                                st.write(f"**{doc_list[i].metadata['source'], doc_list[i].metadata['page']}**")

except URLError as e:
    st.error(
        """
        **This demo requires internet access.**
        Connection error: %s
        """
        % e.reason
    )

