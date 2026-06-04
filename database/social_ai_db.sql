--
-- PostgreSQL database dump
--

\restrict K3tb1eKTtNecXgWejZ2LXcHYnyIiWP8qseVngnxZyUBmxrCMqaYYzxtMI7OMvHv

-- Dumped from database version 18.4
-- Dumped by pg_dump version 18.4

-- Started on 2026-06-04 15:56:02

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- TOC entry 230 (class 1259 OID 16509)
-- Name: ai_settings; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.ai_settings (
    id integer NOT NULL,
    tone character varying(32) DEFAULT 'friendly'::character varying NOT NULL,
    system_prompt text NOT NULL,
    slider_formal integer DEFAULT 40 NOT NULL,
    slider_length integer DEFAULT 50 NOT NULL,
    slider_sales integer DEFAULT 60 NOT NULL,
    response_rules jsonb,
    updated_at timestamp without time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.ai_settings OWNER TO postgres;

--
-- TOC entry 229 (class 1259 OID 16508)
-- Name: ai_settings_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.ai_settings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.ai_settings_id_seq OWNER TO postgres;

--
-- TOC entry 5195 (class 0 OID 0)
-- Dependencies: 229
-- Name: ai_settings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.ai_settings_id_seq OWNED BY public.ai_settings.id;


--
-- TOC entry 238 (class 1259 OID 24603)
-- Name: audit_logs; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.audit_logs (
    id integer NOT NULL,
    user_id integer NOT NULL,
    action character varying(255) NOT NULL,
    resource_type character varying(100),
    resource_id character varying(100),
    changes jsonb,
    ip_address character varying(45),
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.audit_logs OWNER TO postgres;

--
-- TOC entry 237 (class 1259 OID 24602)
-- Name: audit_logs_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.audit_logs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.audit_logs_id_seq OWNER TO postgres;

--
-- TOC entry 5196 (class 0 OID 0)
-- Dependencies: 237
-- Name: audit_logs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.audit_logs_id_seq OWNED BY public.audit_logs.id;


--
-- TOC entry 236 (class 1259 OID 24577)
-- Name: auth_users; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.auth_users (
    id integer NOT NULL,
    email character varying(255) NOT NULL,
    password_hash character varying(255) NOT NULL,
    full_name character varying(255) NOT NULL,
    role character varying(32) DEFAULT 'agent'::character varying NOT NULL,
    status character varying(32) DEFAULT 'active'::character varying NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    last_login timestamp without time zone
);


ALTER TABLE public.auth_users OWNER TO postgres;

--
-- TOC entry 235 (class 1259 OID 24576)
-- Name: auth_users_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.auth_users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.auth_users_id_seq OWNER TO postgres;

--
-- TOC entry 5197 (class 0 OID 0)
-- Dependencies: 235
-- Name: auth_users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.auth_users_id_seq OWNED BY public.auth_users.id;


--
-- TOC entry 232 (class 1259 OID 16534)
-- Name: automation_rules; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.automation_rules (
    id integer NOT NULL,
    name character varying(128) NOT NULL,
    trigger text NOT NULL,
    action text NOT NULL,
    trigger_config jsonb,
    action_config jsonb,
    enabled boolean DEFAULT true NOT NULL,
    sort_order integer DEFAULT 0 NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.automation_rules OWNER TO postgres;

--
-- TOC entry 231 (class 1259 OID 16533)
-- Name: automation_rules_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.automation_rules_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.automation_rules_id_seq OWNER TO postgres;

--
-- TOC entry 5198 (class 0 OID 0)
-- Dependencies: 231
-- Name: automation_rules_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.automation_rules_id_seq OWNED BY public.automation_rules.id;


--
-- TOC entry 240 (class 1259 OID 24625)
-- Name: channels; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.channels (
    id integer NOT NULL,
    channel character varying(32) NOT NULL,
    display_name character varying(64) NOT NULL,
    enabled boolean DEFAULT true NOT NULL,
    webhook_path character varying(128) NOT NULL,
    last_verified_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.channels OWNER TO postgres;

--
-- TOC entry 239 (class 1259 OID 24624)
-- Name: channels_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.channels_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.channels_id_seq OWNER TO postgres;

--
-- TOC entry 5199 (class 0 OID 0)
-- Dependencies: 239
-- Name: channels_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.channels_id_seq OWNED BY public.channels.id;


--
-- TOC entry 222 (class 1259 OID 16409)
-- Name: conversations; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.conversations (
    id integer NOT NULL,
    user_id integer NOT NULL,
    channel character varying(32) NOT NULL,
    status character varying(32) DEFAULT 'active'::character varying NOT NULL,
    ai_enabled boolean DEFAULT true NOT NULL,
    last_message text,
    last_message_at timestamp without time zone,
    unread_count integer DEFAULT 0 NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    assigned_to integer,
    assigned_at timestamp without time zone,
    assigned_by integer,
    resolved_at timestamp without time zone,
    resolved_by integer,
    handoff_reason character varying(64)
);


ALTER TABLE public.conversations OWNER TO postgres;

--
-- TOC entry 221 (class 1259 OID 16408)
-- Name: conversations_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.conversations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.conversations_id_seq OWNER TO postgres;

--
-- TOC entry 5200 (class 0 OID 0)
-- Dependencies: 221
-- Name: conversations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.conversations_id_seq OWNED BY public.conversations.id;


--
-- TOC entry 234 (class 1259 OID 16557)
-- Name: logs; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.logs (
    id integer NOT NULL,
    level character varying(16) NOT NULL,
    source character varying(64) NOT NULL,
    message text NOT NULL,
    conversation_id integer,
    payload jsonb,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.logs OWNER TO postgres;

--
-- TOC entry 233 (class 1259 OID 16556)
-- Name: logs_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.logs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.logs_id_seq OWNER TO postgres;

--
-- TOC entry 5201 (class 0 OID 0)
-- Dependencies: 233
-- Name: logs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.logs_id_seq OWNED BY public.logs.id;


--
-- TOC entry 224 (class 1259 OID 16440)
-- Name: messages; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.messages (
    id integer NOT NULL,
    conversation_id integer NOT NULL,
    user_id integer NOT NULL,
    channel character varying(32) NOT NULL,
    direction character varying(8) NOT NULL,
    sender character varying(16),
    content text NOT NULL,
    intent character varying(64),
    product_keyword character varying(128),
    ai_response_time_ms integer,
    ai_tokens_used integer,
    ai_model character varying(64),
    platform_message_id character varying(256),
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    sender_id integer,
    CONSTRAINT messages_direction_check CHECK (((direction)::text = ANY ((ARRAY['inbound'::character varying, 'outbound'::character varying])::text[])))
);


ALTER TABLE public.messages OWNER TO postgres;

--
-- TOC entry 223 (class 1259 OID 16439)
-- Name: messages_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.messages_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.messages_id_seq OWNER TO postgres;

--
-- TOC entry 5202 (class 0 OID 0)
-- Dependencies: 223
-- Name: messages_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.messages_id_seq OWNED BY public.messages.id;


--
-- TOC entry 226 (class 1259 OID 16474)
-- Name: products_cache; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.products_cache (
    id integer NOT NULL,
    shopify_product_id character varying(64) NOT NULL,
    name character varying(256) NOT NULL,
    description text,
    price numeric(10,2),
    variants jsonb,
    images jsonb,
    tags jsonb,
    cached_at timestamp without time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.products_cache OWNER TO postgres;

--
-- TOC entry 225 (class 1259 OID 16473)
-- Name: products_cache_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.products_cache_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.products_cache_id_seq OWNER TO postgres;

--
-- TOC entry 5203 (class 0 OID 0)
-- Dependencies: 225
-- Name: products_cache_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.products_cache_id_seq OWNED BY public.products_cache.id;


--
-- TOC entry 228 (class 1259 OID 16492)
-- Name: stock_cache; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.stock_cache (
    id integer NOT NULL,
    product_key character varying(256) NOT NULL,
    quantity integer DEFAULT 0 NOT NULL,
    unit character varying(32) DEFAULT 'pcs'::character varying,
    warehouse character varying(128),
    cached_at timestamp without time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.stock_cache OWNER TO postgres;

--
-- TOC entry 227 (class 1259 OID 16491)
-- Name: stock_cache_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.stock_cache_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.stock_cache_id_seq OWNER TO postgres;

--
-- TOC entry 5204 (class 0 OID 0)
-- Dependencies: 227
-- Name: stock_cache_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.stock_cache_id_seq OWNED BY public.stock_cache.id;


--
-- TOC entry 220 (class 1259 OID 16386)
-- Name: users; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.users (
    id integer NOT NULL,
    external_id character varying(128) NOT NULL,
    channel character varying(32) NOT NULL,
    name character varying(128),
    avatar_url character varying(512),
    is_human_handled boolean DEFAULT false NOT NULL,
    ai_disabled boolean DEFAULT false NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.users OWNER TO postgres;

--
-- TOC entry 219 (class 1259 OID 16385)
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.users_id_seq OWNER TO postgres;

--
-- TOC entry 5205 (class 0 OID 0)
-- Dependencies: 219
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;


--
-- TOC entry 4925 (class 2604 OID 16512)
-- Name: ai_settings id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ai_settings ALTER COLUMN id SET DEFAULT nextval('public.ai_settings_id_seq'::regclass);


--
-- TOC entry 4943 (class 2604 OID 24606)
-- Name: audit_logs id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.audit_logs ALTER COLUMN id SET DEFAULT nextval('public.audit_logs_id_seq'::regclass);


--
-- TOC entry 4938 (class 2604 OID 24580)
-- Name: auth_users id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.auth_users ALTER COLUMN id SET DEFAULT nextval('public.auth_users_id_seq'::regclass);


--
-- TOC entry 4931 (class 2604 OID 16537)
-- Name: automation_rules id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.automation_rules ALTER COLUMN id SET DEFAULT nextval('public.automation_rules_id_seq'::regclass);


--
-- TOC entry 4945 (class 2604 OID 24628)
-- Name: channels id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.channels ALTER COLUMN id SET DEFAULT nextval('public.channels_id_seq'::regclass);


--
-- TOC entry 4911 (class 2604 OID 16412)
-- Name: conversations id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.conversations ALTER COLUMN id SET DEFAULT nextval('public.conversations_id_seq'::regclass);


--
-- TOC entry 4936 (class 2604 OID 16560)
-- Name: logs id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.logs ALTER COLUMN id SET DEFAULT nextval('public.logs_id_seq'::regclass);


--
-- TOC entry 4917 (class 2604 OID 16443)
-- Name: messages id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.messages ALTER COLUMN id SET DEFAULT nextval('public.messages_id_seq'::regclass);


--
-- TOC entry 4919 (class 2604 OID 16477)
-- Name: products_cache id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.products_cache ALTER COLUMN id SET DEFAULT nextval('public.products_cache_id_seq'::regclass);


--
-- TOC entry 4921 (class 2604 OID 16495)
-- Name: stock_cache id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.stock_cache ALTER COLUMN id SET DEFAULT nextval('public.stock_cache_id_seq'::regclass);


--
-- TOC entry 4906 (class 2604 OID 16389)
-- Name: users id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
-- TOC entry 5179 (class 0 OID 16509)
-- Dependencies: 230
-- Data for Name: ai_settings; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.ai_settings (id, tone, system_prompt, slider_formal, slider_length, slider_sales, response_rules, updated_at) FROM stdin;
1	friendly	You are a helpful customer support assistant for a Kenyan online fashion and beauty store. You respond in a warm, friendly tone, answer questions about products, pricing, stock, and delivery, and gently encourage customers to place an order when appropriate. Be concise and natural — like a knowledgeable shop assistant, not a robot.	40	50	60	{"use_emoji": true, "auto_greet": true, "mention_delivery_in_kenya": true, "always_offer_alternatives_when_out_of_stock": true}	2026-06-02 13:17:55.965302
\.


--
-- TOC entry 5187 (class 0 OID 24603)
-- Dependencies: 238
-- Data for Name: audit_logs; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.audit_logs (id, user_id, action, resource_type, resource_id, changes, ip_address, created_at) FROM stdin;
1	4	login	\N	\N	null	127.0.0.1	2026-05-28 06:46:38.724239
2	4	login	\N	\N	null	127.0.0.1	2026-05-28 06:47:24.529462
3	5	login	\N	\N	null	127.0.0.1	2026-05-28 06:49:31.395294
4	6	login	\N	\N	null	127.0.0.1	2026-05-28 06:50:30.366579
5	4	login	\N	\N	null	127.0.0.1	2026-05-28 06:53:08.508003
6	4	login	\N	\N	null	127.0.0.1	2026-05-28 07:35:53.1274
7	4	login	\N	\N	null	127.0.0.1	2026-05-28 07:36:32.353747
8	4	login	\N	\N	null	127.0.0.1	2026-05-28 07:40:26.194505
9	4	login	\N	\N	null	127.0.0.1	2026-05-28 07:41:27.485159
10	4	login	\N	\N	null	127.0.0.1	2026-05-28 07:43:44.66495
43	4	login	\N	\N	null	127.0.0.1	2026-05-28 07:58:17.682499
44	4	login	\N	\N	null	127.0.0.1	2026-05-28 08:00:23.409875
45	4	login	\N	\N	null	127.0.0.1	2026-05-28 09:15:15.114493
46	4	login	\N	\N	null	127.0.0.1	2026-05-28 09:21:21.731609
47	4	login	\N	\N	null	127.0.0.1	2026-05-28 11:42:45.419162
48	4	login	\N	\N	null	127.0.0.1	2026-05-28 12:44:28.135716
49	4	login	\N	\N	null	127.0.0.1	2026-05-28 13:10:44.539405
50	4	login	\N	\N	null	127.0.0.1	2026-05-28 13:15:28.461124
51	4	login	\N	\N	null	127.0.0.1	2026-05-28 13:19:18.482721
52	4	login	\N	\N	null	127.0.0.1	2026-05-28 13:22:49.899972
53	4	login	\N	\N	null	127.0.0.1	2026-05-28 13:35:20.137752
54	4	login	\N	\N	null	127.0.0.1	2026-05-28 13:40:35.347176
55	4	login	\N	\N	null	127.0.0.1	2026-05-28 13:40:57.858542
56	4	login	\N	\N	null	127.0.0.1	2026-05-28 13:41:22.542907
57	4	logout	\N	\N	null	127.0.0.1	2026-05-28 13:41:27.704689
58	4	login	\N	\N	null	127.0.0.1	2026-05-28 13:42:01.750256
59	4	login	\N	\N	null	127.0.0.1	2026-05-29 06:08:14.796438
60	4	login	\N	\N	null	127.0.0.1	2026-05-29 07:13:57.177171
61	4	login	\N	\N	null	127.0.0.1	2026-05-29 07:16:12.3251
62	4	login	\N	\N	null	127.0.0.1	2026-05-29 07:31:55.864539
63	4	login	\N	\N	null	127.0.0.1	2026-05-29 07:39:39.286866
64	4	send_reply	conversation	4	{"sender": "human", "content_preview": "Hi Fatuma, your order is on its way — sorry for the delay!"}	127.0.0.1	2026-05-29 07:51:11.220581
65	4	send_reply	conversation	1	{"sender": "ai", "content_preview": "Yes, we have it in Medium! Want to order?"}	127.0.0.1	2026-05-29 07:53:15.19401
66	4	toggle_ai	conversation	1	{"ai_enabled": false}	127.0.0.1	2026-05-29 07:59:04.425232
67	4	toggle_ai	conversation	1	{"ai_enabled": false}	127.0.0.1	2026-05-29 08:00:05.37038
68	4	update_conversation	conversation	4	{"status": "resolved"}	127.0.0.1	2026-05-29 08:03:33.08056
69	4	logout	\N	\N	null	127.0.0.1	2026-05-29 11:38:24.883047
70	4	login	\N	\N	null	127.0.0.1	2026-05-29 11:38:27.315844
71	4	logout	\N	\N	null	127.0.0.1	2026-05-29 12:50:11.623168
72	5	login	\N	\N	null	127.0.0.1	2026-05-29 12:50:26.604238
73	5	logout	\N	\N	null	127.0.0.1	2026-05-29 13:10:39.97298
74	6	login	\N	\N	null	127.0.0.1	2026-05-29 13:10:56.58625
75	6	logout	\N	\N	null	127.0.0.1	2026-05-29 13:11:33.607687
76	4	login	\N	\N	null	127.0.0.1	2026-05-29 13:11:45.055356
77	4	login	\N	\N	null	127.0.0.1	2026-06-02 05:34:51.118395
78	4	login	\N	\N	null	127.0.0.1	2026-06-02 05:52:32.726064
79	4	toggle_ai	conversation	1	{"ai_enabled": true}	127.0.0.1	2026-06-02 06:11:07.791677
80	4	toggle_ai	conversation	1	{"ai_enabled": false}	127.0.0.1	2026-06-02 06:11:11.911004
81	4	send_reply	conversation	2	{"sender": "human", "content_preview": "agent test reply"}	127.0.0.1	2026-06-02 06:22:40.804638
82	4	update_conversation	conversation	2	{"status": "resolved"}	127.0.0.1	2026-06-02 06:26:42.165845
83	4	update_conversation	conversation	2	{"status": "active"}	127.0.0.1	2026-06-02 06:27:17.293691
84	4	update_conversation	conversation	2	{"status": "resolved"}	127.0.0.1	2026-06-02 06:27:39.585432
85	4	toggle_ai	conversation	11	{"ai_enabled": true}	127.0.0.1	2026-06-02 07:15:10.897691
86	4	toggle_ai	conversation	11	{"ai_enabled": false}	127.0.0.1	2026-06-02 07:20:50.182781
87	4	toggle_ai	conversation	11	{"ai_enabled": true}	127.0.0.1	2026-06-02 07:20:55.425198
88	4	sync_products	products	\N	{"added": 5, "removed": 0, "updated": 0}	127.0.0.1	2026-06-02 07:58:30.03879
89	4	sync_products	products	\N	{"added": 0, "removed": 0, "updated": 0}	127.0.0.1	2026-06-02 08:05:07.948877
90	4	sync_products	products	\N	{"added": 5, "removed": 0, "updated": 0}	127.0.0.1	2026-06-02 12:23:58.13594
91	4	sync_products	products	\N	{"added": 562, "removed": 0, "updated": 0}	127.0.0.1	2026-06-02 12:32:33.859925
92	4	sync_products	products	\N	{"added": 0, "removed": 0, "updated": 0}	127.0.0.1	2026-06-02 12:36:44.070386
93	4	update_ai_settings	ai_settings	1	{"tone": "luxury", "slider_sales": 80}	127.0.0.1	2026-06-02 13:10:25.013073
94	4	update_ai_settings	ai_settings	1	{"response_rules": "<updated>"}	127.0.0.1	2026-06-02 13:16:49.903602
95	4	reset_ai_settings	ai_settings	1	null	127.0.0.1	2026-06-02 13:17:55.968982
96	4	login	\N	\N	null	127.0.0.1	2026-06-03 05:43:22.711519
97	4	login	\N	\N	null	127.0.0.1	2026-06-03 07:56:43.248664
98	4	create_automation_rule	automation_rule	7	{"name": "Bridal Greeting"}	127.0.0.1	2026-06-03 07:59:49.293891
99	4	toggle_automation_rule	automation_rule	5	{"enabled": true}	127.0.0.1	2026-06-03 08:06:45.413389
100	4	update_automation_rule	automation_rule	1	{"name": "Price Reply (KE)", "enabled": true}	127.0.0.1	2026-06-03 08:09:28.611926
101	4	reorder_automation_rules	automation_rules	\N	{"order": [7, 1, 2, 3, 4, 5, 6]}	127.0.0.1	2026-06-03 08:12:59.488722
102	4	delete_automation_rule	automation_rule	7	{"name": "Bridal Greeting"}	127.0.0.1	2026-06-03 08:18:02.208681
103	5	login	\N	\N	null	127.0.0.1	2026-06-03 08:55:44.659045
104	6	login	\N	\N	null	127.0.0.1	2026-06-03 09:00:28.258614
105	6	login	\N	\N	null	127.0.0.1	2026-06-03 09:07:05.121882
106	4	login	\N	\N	null	127.0.0.1	2026-06-03 09:10:18.645002
107	4	logout	\N	\N	null	127.0.0.1	2026-06-03 09:12:00.336829
108	6	login	\N	\N	null	127.0.0.1	2026-06-03 09:17:34.842646
109	5	login	\N	\N	null	127.0.0.1	2026-06-03 09:20:02.391129
110	4	login	\N	\N	null	127.0.0.1	2026-06-03 09:24:36.986279
111	4	login	\N	\N	null	127.0.0.1	2026-06-03 11:28:55.224428
112	4	logout	\N	\N	null	127.0.0.1	2026-06-03 11:34:47.00328
113	5	login	\N	\N	null	127.0.0.1	2026-06-03 11:34:59.357392
114	5	logout	\N	\N	null	127.0.0.1	2026-06-03 11:41:38.830659
115	6	login	\N	\N	null	127.0.0.1	2026-06-03 11:41:54.656825
116	6	logout	\N	\N	null	127.0.0.1	2026-06-03 11:44:30.097792
117	4	login	\N	\N	null	127.0.0.1	2026-06-03 11:44:42.448339
118	4	login	\N	\N	null	127.0.0.1	2026-06-03 11:59:15.837944
119	4	create_user	user	7	{"role": "agent", "email": "duck@example.com", "full_name": "Donald Duck"}	127.0.0.1	2026-06-03 12:04:15.968278
120	4	toggle_ai	conversation	8	{"ai_enabled": false}	127.0.0.1	2026-06-03 12:19:31.020315
121	4	toggle_ai	conversation	8	{"ai_enabled": true}	127.0.0.1	2026-06-03 12:19:34.468504
122	4	toggle_ai	conversation	8	{"ai_enabled": false}	127.0.0.1	2026-06-03 12:21:59.682802
123	4	toggle_ai	conversation	8	{"ai_enabled": true}	127.0.0.1	2026-06-03 12:22:03.667479
124	4	toggle_ai	conversation	13	{"ai_enabled": false}	127.0.0.1	2026-06-03 12:25:52.518046
125	4	toggle_ai	conversation	13	{"ai_enabled": true}	127.0.0.1	2026-06-03 12:25:53.877022
126	4	toggle_ai	conversation	13	{"ai_enabled": false}	127.0.0.1	2026-06-03 12:28:45.246461
127	4	toggle_ai	conversation	13	{"ai_enabled": true}	127.0.0.1	2026-06-03 12:28:47.341151
128	4	toggle_ai	conversation	13	{"ai_enabled": false}	127.0.0.1	2026-06-03 12:28:49.560895
129	4	toggle_ai	conversation	13	{"ai_enabled": true}	127.0.0.1	2026-06-03 12:28:50.640593
130	4	toggle_ai	conversation	13	{"ai_enabled": false}	127.0.0.1	2026-06-03 12:28:51.846179
131	4	toggle_ai	conversation	13	{"ai_enabled": true}	127.0.0.1	2026-06-03 12:28:53.400709
132	4	toggle_ai	conversation	4	{"ai_enabled": true}	127.0.0.1	2026-06-03 14:01:05.549091
133	4	toggle_ai	conversation	4	{"ai_enabled": false}	127.0.0.1	2026-06-03 14:01:06.684729
134	4	logout	\N	\N	null	127.0.0.1	2026-06-03 14:02:20.912119
135	5	login	\N	\N	null	127.0.0.1	2026-06-03 14:02:27.602211
136	5	logout	\N	\N	null	127.0.0.1	2026-06-03 14:03:15.439683
137	6	login	\N	\N	null	127.0.0.1	2026-06-03 14:03:20.858108
138	6	logout	\N	\N	null	127.0.0.1	2026-06-03 14:04:05.944676
139	4	login	\N	\N	null	127.0.0.1	2026-06-03 14:04:12.063114
140	4	logout	\N	\N	null	127.0.0.1	2026-06-04 05:51:05.934277
141	4	login	\N	\N	null	127.0.0.1	2026-06-04 05:51:12.50147
142	4	sync_products	products	\N	{"added": 5, "removed": 562, "updated": 0}	127.0.0.1	2026-06-04 05:59:15.800716
143	4	sync_products	products	\N	{"added": 0, "removed": 0, "updated": 0}	127.0.0.1	2026-06-04 05:59:55.097441
144	4	login	\N	\N	null	127.0.0.1	2026-06-04 06:24:01.806657
145	4	logout	\N	\N	null	127.0.0.1	2026-06-04 06:35:03.786496
146	5	login	\N	\N	null	127.0.0.1	2026-06-04 06:35:11.337114
147	5	logout	\N	\N	null	127.0.0.1	2026-06-04 06:36:35.654248
148	6	login	\N	\N	null	127.0.0.1	2026-06-04 06:36:39.876852
149	6	logout	\N	\N	null	127.0.0.1	2026-06-04 06:37:01.964746
150	4	login	\N	\N	null	127.0.0.1	2026-06-04 06:37:06.8352
151	4	logout	\N	\N	null	127.0.0.1	2026-06-04 06:39:36.911479
152	5	login	\N	\N	null	127.0.0.1	2026-06-04 06:39:40.990302
153	5	logout	\N	\N	null	127.0.0.1	2026-06-04 06:40:12.2037
154	6	login	\N	\N	null	127.0.0.1	2026-06-04 06:40:16.728351
155	6	logout	\N	\N	null	127.0.0.1	2026-06-04 06:44:16.636463
156	4	login	\N	\N	null	127.0.0.1	2026-06-04 06:44:20.777907
157	4	logout	\N	\N	null	127.0.0.1	2026-06-04 06:46:58.495573
158	4	login	\N	\N	null	127.0.0.1	2026-06-04 06:47:00.602027
159	4	login	\N	\N	null	127.0.0.1	2026-06-04 09:56:24.819657
160	4	login	\N	\N	null	127.0.0.1	2026-06-04 07:12:35.202786
161	4	update_channel	channel	1	{"enabled": false}	127.0.0.1	2026-06-04 07:16:48.996765
162	4	update_channel	channel	1	{"enabled": true}	127.0.0.1	2026-06-04 07:29:35.194523
163	4	update_channel	channel	1	{"enabled": false}	127.0.0.1	2026-06-04 07:29:36.724733
164	4	test_channel	channel	2	{"result": "ok_mocked"}	127.0.0.1	2026-06-04 07:48:40.074243
165	4	assign_conversation	conversation	2	{"assigned_to": 4, "assigned_to_email": "admin@company.com"}	127.0.0.1	2026-06-04 08:43:25.96599
166	6	login	\N	\N	null	127.0.0.1	2026-06-04 08:46:52.717747
167	5	login	\N	\N	null	127.0.0.1	2026-06-04 08:47:03.525746
168	4	login	\N	\N	null	127.0.0.1	2026-06-04 08:47:11.812883
169	4	assign_conversation	conversation	2	{"assigned_to": 5, "assigned_to_email": "agent@company.com"}	127.0.0.1	2026-06-04 08:47:24.871424
170	4	assign_conversation	conversation	1	{"assigned_to": 5, "assigned_to_email": "agent@company.com"}	127.0.0.1	2026-06-04 08:48:01.047708
171	4	assign_conversation	conversation	3	{"assigned_to": 5, "assigned_to_email": "agent@company.com"}	127.0.0.1	2026-06-04 08:48:20.680541
172	4	assign_conversation	conversation	2	{"assigned_to": 6, "assigned_to_email": "supervisor@company.com"}	127.0.0.1	2026-06-04 08:48:46.793563
173	4	unassign_conversation	conversation	2	{"previous_assigned_to": 6}	127.0.0.1	2026-06-04 08:49:47.58528
174	5	login	\N	\N	null	127.0.0.1	2026-06-04 08:50:26.984572
175	5	assign_conversation	conversation	2	{"assigned_to": 5, "assigned_to_email": "agent@company.com"}	127.0.0.1	2026-06-04 08:52:28.767313
176	4	login	\N	\N	null	127.0.0.1	2026-06-04 08:57:44.573437
177	4	update_channel	channel	1	{"enabled": true}	127.0.0.1	2026-06-04 09:25:50.074191
\.


--
-- TOC entry 5185 (class 0 OID 24577)
-- Dependencies: 236
-- Data for Name: auth_users; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.auth_users (id, email, password_hash, full_name, role, status, created_at, updated_at, last_login) FROM stdin;
7	duck@example.com	$2b$12$jQn6mQBuI1y.MsAQO1vAIuyjcxuTD27DPBFu7Bx3rsKES4hQ5w9DG	Donald Duck	agent	active	2026-06-03 12:04:15.957991	2026-06-03 12:04:15.957991	\N
6	supervisor@company.com	$2b$12$JKY9npxEjczxoOHXj0tMHeR1trqlfn4U..Ou5.sSoq0F6Yn4yVuxe	Bob Supervisor	supervisor	active	2026-05-28 06:46:18.344302	2026-06-04 08:46:52.709398	2026-06-04 11:46:52.709398
5	agent@company.com	$2b$12$QkMlZxoZeqvv3onT8X6s0u3b5vCyB2VW9iEBe2NO.Vc/uvSMNWJuO	Jane Agent	agent	active	2026-05-28 06:46:18.344302	2026-06-04 08:50:26.984572	2026-06-04 11:50:26.984572
4	admin@company.com	$2b$12$/4xUPtUIn3D3Oe3TEIWsC.sy28df6SB84VdTwYF20mwPT5tN7V2lK	Admin User	admin	active	2026-05-28 06:46:18.344302	2026-06-04 08:57:44.524133	2026-06-04 11:57:44.523121
\.


--
-- TOC entry 5181 (class 0 OID 16534)
-- Dependencies: 232
-- Data for Name: automation_rules; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.automation_rules (id, name, trigger, action, trigger_config, action_config, enabled, sort_order, created_at, updated_at) FROM stdin;
1	Price Reply (KE)	Message contains: "price", "how much", "bei", "ksh"	Always include price from Shopify in reply	{"type": "keyword", "keywords": ["price", "how much", "bei", "ksh"]}	{"type": "include_price"}	t	2	2026-05-25 10:52:27.486227	2026-06-03 08:12:59.454597
3	Comment → DM	Instagram or Facebook comment contains: "price?", "how much?"	Reply publicly: "Check your DMs!" + trigger DM flow	{"type": "keyword", "channels": ["instagram_comment", "facebook_comment"], "keywords": ["price?", "how much?"]}	{"type": "trigger_dm_flow", "public_reply": "Hey! 👋 We've sent you a DM with all the details. Check your inbox! 💌"}	t	4	2026-05-25 10:52:27.486227	2026-06-03 08:12:59.454597
4	After Hours	Any message (always on)	Auto-reply normally — no after-hours delay	{"type": "always"}	{"type": "normal_reply"}	t	5	2026-05-25 10:52:27.486227	2026-06-03 08:12:59.454597
5	Complaint Escalate	Intent = complaint	Flag for human review + send empathy reply	{"type": "intent", "intent": "complaint"}	{"type": "human_escalate", "empathy_reply": true}	t	6	2026-05-25 10:52:27.486227	2026-06-03 08:12:59.454597
6	Order Status	Intent = order_status	Ask for order number + flag for human follow-up	{"type": "intent", "intent": "order_status"}	{"type": "ask_order_number", "flag_human": true}	t	7	2026-05-25 10:52:27.486227	2026-06-03 08:12:59.454597
2	Out of Stock	Shopify stock = 0	Reply: "Currently out of stock" + suggest similar product	{"type": "shopify_stock", "value": 0, "condition": "eq"}	{"type": "reply_template", "template": "This item is currently out of stock. Would you like to be notified when it's back? 📦", "suggest_similar": true}	t	3	2026-05-25 10:52:27.486227	2026-06-03 08:12:59.454597
\.


--
-- TOC entry 5189 (class 0 OID 24625)
-- Dependencies: 240
-- Data for Name: channels; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.channels (id, channel, display_name, enabled, webhook_path, last_verified_at, created_at, updated_at) FROM stdin;
3	whatsapp	WhatsApp	t	/webhook/whatsapp	\N	2026-05-29 11:47:09.098923	2026-05-29 11:47:09.098923
4	facebook_dm	Facebook Messenger	t	/webhook/facebook	\N	2026-05-29 11:47:09.098923	2026-05-29 11:47:09.098923
5	facebook_comment	Facebook Comments	t	/webhook/facebook/comments	\N	2026-05-29 11:47:09.098923	2026-05-29 11:47:09.098923
6	tiktok_dm	TikTok DMs	t	/webhook/tiktok	\N	2026-05-29 11:47:09.098923	2026-05-29 11:47:09.098923
7	tiktok_comment	TikTok Comments	t	/webhook/tiktok/comments	\N	2026-05-29 11:47:09.098923	2026-05-29 11:47:09.098923
2	instagram_comment	Instagram Comments	t	/webhook/instagram/comments	2026-06-04 10:48:40.061858	2026-05-29 11:47:09.098923	2026-06-04 07:48:40.063871
1	instagram_dm	Instagram DMs	t	/webhook/instagram	\N	2026-05-29 11:47:09.098923	2026-06-04 12:25:49.9752
\.


--
-- TOC entry 5171 (class 0 OID 16409)
-- Dependencies: 222
-- Data for Name: conversations; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.conversations (id, user_id, channel, status, ai_enabled, last_message, last_message_at, unread_count, created_at, updated_at, assigned_to, assigned_at, assigned_by, resolved_at, resolved_by, handoff_reason) FROM stdin;
5	5	whatsapp	active	t	Yes! We deliver nationwide including Mombasa 🚚	2026-05-28 15:47:54.007103	0	2026-05-28 16:18:54.007103	2026-05-28 16:18:54.007103	\N	\N	\N	\N	\N	\N
6	6	facebook_dm	active	t	Yes, we ship nationwide including Kisumu! 🚚	2026-05-28 16:07:54.007103	0	2026-05-28 16:18:54.007103	2026-05-28 16:18:54.007103	\N	\N	\N	\N	\N	\N
11	10	instagram_dm	human_override	t	hello? anyone there?	2026-06-02 07:10:16.732962	0	2026-06-02 06:57:12.005477	2026-06-02 07:20:55.407467	\N	\N	\N	\N	\N	\N
12	11	instagram_dm	active	t	Hi there! 👋 Welcome to our store. Yes, the Black Wrap Dress is available — we have 8 units in stock! ✅ It comes in: XS, S, M, L, XL. Would you like to place an order? 😊	2026-06-02 07:07:57.011636	0	2026-06-02 07:07:56.942402	2026-06-02 07:20:57.612471	\N	\N	\N	\N	\N	\N
7	7	facebook_comment	active	t	Check your inbox! 💌	2026-05-28 16:03:54.007103	0	2026-05-28 16:18:54.007103	2026-06-02 13:46:18.824494	\N	\N	\N	\N	\N	\N
8	8	tiktok_dm	active	t	Want me to reserve one for you?	2026-05-28 16:11:54.007103	0	2026-05-28 16:18:54.007103	2026-06-03 12:22:03.657235	\N	\N	\N	\N	\N	\N
13	12	instagram_dm	active	t	Hi! 💍 We have a dedicated bridal collection — check it out here: shopzetu.com/collections/bridal	2026-06-03 08:16:34.579255	0	2026-06-03 08:16:34.464656	2026-06-03 12:28:53.38398	\N	\N	\N	\N	\N	\N
4	4	instagram_dm	resolved	f	Hi Fatuma, your order is on its way — sorry for the delay!	2026-05-29 07:51:11.216035	0	2026-05-28 16:18:54.007103	2026-06-03 14:01:06.666044	\N	\N	\N	\N	\N	\N
1	1	instagram_dm	active	f	Yes, we have it in Medium! Want to order?	2026-05-29 07:53:15.185867	0	2026-05-28 16:18:54.007103	2026-06-04 08:48:01.038282	5	2026-06-04 08:48:01.038282	4	\N	\N	\N
3	3	instagram_comment	active	t	Check your inbox! 💌	2026-05-28 16:03:54.007103	0	2026-05-28 16:18:54.007103	2026-06-04 08:48:20.674135	5	2026-06-04 08:48:20.674135	4	\N	\N	\N
2	2	whatsapp	resolved	t	agent test reply	2026-06-02 06:22:40.784556	0	2026-05-28 16:18:54.007103	2026-06-04 08:52:28.765485	5	2026-06-04 08:52:28.765485	5	2026-06-02 06:27:39.581632	4	\N
18	17	instagram_dm	human_override	f	Thanks for reaching out — I'm connecting you with a member of our team who'll get back to you shortly. We appreciate your patience.	2026-06-04 10:35:34.226382	0	2026-06-04 10:35:33.910998	2026-06-04 10:46:13.795367	7	2026-06-04 10:35:34.113494	\N	\N	\N	keyword
\.


--
-- TOC entry 5183 (class 0 OID 16557)
-- Dependencies: 234
-- Data for Name: logs; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.logs (id, level, source, message, conversation_id, payload, created_at) FROM stdin;
1	info	services	Inbound [instagram_dm] from test_user_keyword_1: I want a refund for my order, this is broken!	\N	\N	2026-06-02 06:47:14.133872
2	info	services	Intents detected: ['greeting', 'order_status', 'complaint']	\N	\N	2026-06-02 06:47:14.224768
4	info	handoff	Conversation 9 handed off — keyword: refund	\N	\N	2026-06-02 06:47:14.265759
5	info	integrations.meta	[MOCK] Instagram reply to test_user_keyword_1: Thanks for reaching out — I'm connecting you with a member of our team who'll ge	\N	\N	2026-06-02 06:47:14.269965
3	info	handoff	Handoff triggered (keyword: refund)	\N	{"detail": "refund", "reason": "keyword"}	2026-06-02 06:47:14.257621
6	info	services	Inbound [instagram_dm] from test_user_keyword_1: I want a refund for my order, this is broken!	\N	\N	2026-06-02 06:57:11.963815
7	info	services	Intents detected: ['greeting', 'order_status', 'complaint']	\N	\N	2026-06-02 06:57:12.032531
8	info	handoff	Handoff triggered (keyword: refund)	11	{"detail": "refund", "reason": "keyword"}	2026-06-02 06:57:12.075727
9	info	handoff	Conversation 11 handed off — keyword: refund	\N	\N	2026-06-02 06:57:12.084194
10	info	integrations.meta	[MOCK] Instagram reply to test_user_keyword_1: Thanks for reaching out — I'm connecting you with a member of our team who'll ge	\N	\N	2026-06-02 06:57:12.084194
11	info	services	Inbound [instagram_dm] from test_user_keyword_1: I want a refund for my order, this is broken!	\N	\N	2026-06-02 06:57:36.845553
12	info	services	AI suppressed for [instagram_dm] test_user_keyword_1 (channel disabled or conversation handed over)	\N	\N	2026-06-02 06:57:36.866426
13	info	services	Inbound [instagram_dm] from test_user_normal_1: Hi! Do you have the black dress in medium?	\N	\N	2026-06-02 07:07:56.932442
14	info	services	Intents detected: ['greeting', 'stock_inquiry', 'product_inquiry']	\N	\N	2026-06-02 07:07:56.956842
15	info	integrations.shopify	Mock product found for 'black'	\N	\N	2026-06-02 07:07:56.98571
16	info	integrations.shopify	Mock product found for 'black'	\N	\N	2026-06-02 07:07:56.98571
17	info	services	Shopify product+stock fetched for keyword: 'black'	\N	\N	2026-06-02 07:07:57.001371
18	info	integrations.meta	[MOCK] Instagram reply to test_user_normal_1: Hi there! 👋 Welcome to our store. Yes, the Black Wrap Dress is available — we ha	\N	\N	2026-06-02 07:07:57.005871
19	info	services	Inbound [instagram_dm] from test_user_keyword_1: hello? anyone there?	\N	\N	2026-06-02 07:10:16.723175
20	info	services	AI suppressed for [instagram_dm] test_user_keyword_1 (channel disabled or conversation handed over)	\N	\N	2026-06-02 07:10:16.750295
21	info	integrations.shopify	Mock catalog: 5 products	\N	\N	2026-06-02 07:58:29.927387
22	info	integrations.shopify	Mock catalog: 5 products	\N	\N	2026-06-02 08:04:24.606141
23	info	integrations.shopify	Mock catalog: 5 products	\N	\N	2026-06-02 08:05:07.939087
24	info	integrations.shopify	Mock catalog: 5 products	\N	\N	2026-06-02 12:23:57.905694
25	info	integrations.shopify	Access token obtained (expires at 2026-06-03T12:27:10.576913)	\N	\N	2026-06-02 12:27:11.580806
26	error	integrations.shopify	Failed to fetch catalog: HTTPSConnectionPool(host='shopzetudev.myshopify.com', port=443): Read timed out. (read timeout=10)	\N	\N	2026-06-02 12:27:21.783846
27	info	integrations.shopify	Access token obtained (expires at 2026-06-03T12:32:17.074707)	\N	\N	2026-06-02 12:32:18.077218
28	info	integrations.shopify	Fetched 562 products from Shopify	\N	\N	2026-06-02 12:32:33.629281
29	info	integrations.shopify	Fetched 562 products from Shopify	\N	\N	2026-06-02 12:36:15.996224
30	info	integrations.shopify	Fetched 562 products from Shopify	\N	\N	2026-06-02 12:36:43.851464
31	info	services	Inbound [instagram_dm] from test_template_user_1: Do you have wedding dresses?	\N	\N	2026-06-03 08:16:34.420133
32	info	services	Intents detected: ['stock_inquiry', 'product_inquiry']	\N	\N	2026-06-03 08:16:34.52817
33	info	integrations.meta	[MOCK] Instagram reply to test_template_user_1: Hi! 💍 We have a dedicated bridal collection — check it out here: shopzetu.com/co	\N	\N	2026-06-03 08:16:34.575787
34	info	services	Template-rule reply used for [instagram_dm] test_template_user_1	\N	\N	2026-06-03 08:16:34.600306
35	info	integrations.shopify	Access token obtained (expires at 2026-06-05T05:51:40.049103)	\N	\N	2026-06-04 05:51:41.050147
36	error	integrations.shopify	Failed to fetch catalog: 404 Client Error: Not Found for url: https://shopzetudev.myshopify.com/admin/api/2024-01/products.json?limit=250	\N	\N	2026-06-04 05:51:41.494134
37	error	integrations.shopify	Failed to fetch catalog: 404 Client Error: Not Found for url: https://shopzetudev.myshopify.com/admin/api/2024-01/products.json?limit=250	\N	\N	2026-06-04 05:54:24.344794
38	info	integrations.shopify	Mock catalog: 5 products	\N	\N	2026-06-04 05:59:15.056355
39	info	integrations.shopify	Mock catalog: 5 products	\N	\N	2026-06-04 05:59:54.991555
40	info	integrations.shopify	Requesting access token from https://shopzetudev.myshopify.com/admin/oauth/access_token	\N	\N	2026-06-04 06:03:03.130442
41	info	integrations.shopify	Access token obtained (expires at 2026-06-05T06:03:02.676617)	\N	\N	2026-06-04 06:03:03.6899
42	error	integrations.shopify	Failed to fetch catalog: 404 Client Error: Not Found for url: https://shopzetudev.myshopify.com/admin/api/2024-01/products.json?limit=250	\N	\N	2026-06-04 06:03:04.174512
43	info	services	Inbound [instagram_dm] from auto_assign_test_user: I want a refund this is broken!	\N	\N	2026-06-04 09:03:03.510912
44	error	services._save_message	name 'utc_now' is not defined	\N	\N	2026-06-04 09:03:03.542819
45	info	services	AI suppressed for [instagram_dm] auto_assign_test_user (channel disabled or conversation handed over)	\N	\N	2026-06-04 09:03:03.555995
46	info	services	Inbound [instagram_dm] from auto_assign_test_user: I want a refund this is broken!	\N	\N	2026-06-04 09:06:21.029937
47	error	services._save_message	name 'utc_now' is not defined	\N	\N	2026-06-04 09:06:21.038234
48	info	services	AI suppressed for [instagram_dm] auto_assign_test_user (channel disabled or conversation handed over)	\N	\N	2026-06-04 09:06:21.043878
49	info	services	Inbound [instagram_dm] from auto_assign_test_user: I want a refund this is broken!	\N	\N	2026-06-04 09:20:49.63517
50	info	services	AI suppressed for [instagram_dm] auto_assign_test_user (channel disabled or conversation handed over)	\N	\N	2026-06-04 09:20:49.898219
51	info	services	Inbound [instagram_dm] from auto_assign_test_user: I want a refund this is broken!	\N	\N	2026-06-04 09:21:27.877162
52	info	services	AI suppressed for [instagram_dm] auto_assign_test_user (channel disabled or conversation handed over)	\N	\N	2026-06-04 09:21:28.122764
53	info	services	Inbound [instagram_dm] from auto_assign_test_user: I want a refund this is broken!	\N	\N	2026-06-04 09:23:52.693062
54	info	services	AI suppressed for [instagram_dm] auto_assign_test_user (channel disabled or conversation handed over)	\N	\N	2026-06-04 09:23:52.821769
55	info	services	Inbound [instagram_dm] from auto_assign_test_user: I want a refund this is broken!	\N	\N	2026-06-04 09:26:01.53755
56	info	services	Intents detected: ['greeting', 'complaint']	\N	\N	2026-06-04 09:26:01.675912
57	error	services._check_handoff_for_inbound	type object 'datetime.datetime' has no attribute 'utc_now'	\N	\N	2026-06-04 09:26:01.836206
58	info	integrations.meta	[MOCK] Instagram reply to auto_assign_test_user: Hi there! 👋 Welcome to our store. I'm really sorry to hear that 😔 Please DM us y	\N	\N	2026-06-04 09:26:01.935659
59	info	services	Inbound [instagram_dm] from auto_assign_test_user: I want a refund this is broken!	\N	\N	2026-06-04 10:35:33.882306
60	info	services	Intents detected: ['greeting', 'complaint']	\N	\N	2026-06-04 10:35:33.973673
61	info	handoff	Auto-assigned conversation 18 to agent duck@example.com	\N	\N	2026-06-04 10:35:34.115494
62	info	handoff	Handoff triggered (keyword: refund)	18	{"detail": "refund", "reason": "keyword"}	2026-06-04 10:35:34.11945
63	info	handoff	Conversation 18 handed off — keyword: refund	\N	\N	2026-06-04 10:35:34.202844
64	info	integrations.meta	[MOCK] Instagram reply to auto_assign_test_user: Thanks for reaching out — I'm connecting you with a member of our team who'll ge	\N	\N	2026-06-04 10:35:34.221435
\.


--
-- TOC entry 5173 (class 0 OID 16440)
-- Dependencies: 224
-- Data for Name: messages; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.messages (id, conversation_id, user_id, channel, direction, sender, content, intent, product_keyword, ai_response_time_ms, ai_tokens_used, ai_model, platform_message_id, created_at, sender_id) FROM stdin;
1	1	1	instagram_dm	inbound	\N	Hi! Do you have the black dress in medium?	\N	\N	\N	\N	\N	\N	2026-05-28 16:13:54.007103	\N
2	1	1	instagram_dm	outbound	ai	Hi there! 👋 Yes, the Black Wrap Dress is available in Medium. We have 8 units in stock. Would you like to place an order?	stock_inquiry	Black Wrap Dress	1100	\N	claude	\N	2026-05-28 16:14:54.007103	\N
3	1	1	instagram_dm	inbound	\N	What colors does it come in?	\N	\N	\N	\N	\N	\N	2026-05-28 16:15:54.007103	\N
4	1	1	instagram_dm	outbound	ai	The Black Wrap Dress comes in Black, Burgundy, and Olive Green. Which color catches your eye? 😊	product_inquiry	Black Wrap Dress	900	\N	claude	\N	2026-05-28 16:16:54.007103	\N
5	2	2	whatsapp	inbound	\N	Hello, how much is the vitamin C serum?	\N	\N	\N	\N	\N	\N	2026-05-28 16:06:54.007103	\N
6	2	2	whatsapp	outbound	ai	Hi! The Vitamin C Brightening Serum is KES 2,200 for 30ml and KES 3,100 for 50ml. ✨ Would you like to order?	price_inquiry	Vitamin C Serum	900	\N	claude	\N	2026-05-28 16:07:54.007103	\N
7	2	2	whatsapp	inbound	\N	Is it in stock?	\N	\N	\N	\N	\N	\N	2026-05-28 16:08:54.007103	\N
8	2	2	whatsapp	outbound	ai	Unfortunately the Vitamin C Serum is currently out of stock 😔 Would you like me to notify you when it's back?	stock_inquiry	Vitamin C Serum	1000	\N	claude	\N	2026-05-28 16:09:54.007103	\N
9	3	3	instagram_comment	inbound	\N	price? 👀	\N	\N	\N	\N	\N	\N	2026-05-28 16:02:54.007103	\N
10	3	3	instagram_comment	outbound	ai	Hey! 👋 We've sent you a DM with all the details. Check your inbox! 💌	price_inquiry	Unknown	700	\N	claude	\N	2026-05-28 16:03:54.007103	\N
11	4	4	instagram_dm	inbound	\N	Hi, my order #KE2041 hasn't arrived yet. It's been 5 days.	\N	\N	\N	\N	\N	\N	2026-05-28 15:53:54.007103	\N
12	4	4	instagram_dm	outbound	ai	I'm sorry to hear that! Please share your order number and I'll look it up for you.	order_status	\N	1200	\N	claude	\N	2026-05-28 15:54:54.007103	\N
13	4	4	instagram_dm	inbound	\N	I already gave it — #KE2041	\N	\N	\N	\N	\N	\N	2026-05-28 15:55:54.007103	\N
14	4	4	instagram_dm	outbound	human	(Agent took over) Hi Fatuma, I'm checking on order #KE2041 right now. Give me 2 minutes!	\N	\N	\N	\N	\N	\N	2026-05-28 15:56:54.007103	\N
15	5	5	whatsapp	inbound	\N	Do you deliver to Mombasa?	\N	\N	\N	\N	\N	\N	2026-05-28 15:46:54.007103	\N
16	5	5	whatsapp	outbound	ai	Yes! We deliver nationwide including Mombasa 🚚 Delivery takes 2–3 business days and costs KES 350. Would you like to place an order?	delivery_inquiry	\N	1300	\N	claude	\N	2026-05-28 15:47:54.007103	\N
17	6	6	facebook_dm	inbound	\N	Hi! Do you ship to Kisumu?	\N	\N	\N	\N	\N	\N	2026-05-28 16:06:54.007103	\N
18	6	6	facebook_dm	outbound	ai	Yes, we ship nationwide including Kisumu! 🚚 Delivery takes 2–3 business days and costs KES 350. Is there a specific product you'd like to order?	delivery_inquiry	\N	1000	\N	claude	\N	2026-05-28 16:07:54.007103	\N
19	7	7	facebook_comment	inbound	\N	price? 🔥	\N	\N	\N	\N	\N	\N	2026-05-28 16:02:54.007103	\N
20	7	7	facebook_comment	outbound	ai	Hey Wanjiru! 👋 We've sent you a DM with all the pricing details. Check your inbox! 💌	price_inquiry	Unknown	800	\N	claude	\N	2026-05-28 16:03:54.007103	\N
21	8	8	tiktok_dm	inbound	\N	Hi! Is the black dress available in size M?	\N	\N	\N	\N	\N	\N	2026-05-28 16:10:54.007103	\N
22	8	8	tiktok_dm	outbound	ai	Hey! Yes, the Black Wrap Dress is in stock in Medium 🖤 Want me to reserve one for you?	stock_inquiry	Black Wrap Dress	1000	\N	claude	\N	2026-05-28 16:11:54.007103	\N
23	4	4	instagram_dm	outbound	human	Hi Fatuma, your order is on its way — sorry for the delay!	\N	\N	\N	\N	\N	\N	2026-05-29 07:51:11.216035	\N
24	1	1	instagram_dm	outbound	ai	Yes, we have it in Medium! Want to order?	\N	\N	\N	\N	\N	\N	2026-05-29 07:53:15.185867	\N
25	2	2	whatsapp	outbound	human	agent test reply	\N	\N	\N	\N	\N	\N	2026-06-02 06:22:40.784556	4
28	11	10	instagram_dm	inbound	\N	I want a refund for my order, this is broken!	greeting|order_status|complaint	\N	\N	\N	\N	\N	2026-06-02 06:57:12.015779	\N
29	11	10	instagram_dm	outbound	ai	Thanks for reaching out — I'm connecting you with a member of our team who'll get back to you shortly. We appreciate your patience.	\N	\N	\N	\N	\N	\N	2026-06-02 06:57:12.102008	\N
30	11	10	instagram_dm	inbound	\N	I want a refund for my order, this is broken!	\N	\N	\N	\N	\N	\N	2026-06-02 06:57:36.855252	\N
31	12	11	instagram_dm	inbound	\N	Hi! Do you have the black dress in medium?	greeting|stock_inquiry|product_inquiry	\N	\N	\N	\N	\N	2026-06-02 07:07:56.946346	\N
32	12	11	instagram_dm	outbound	ai	Hi there! 👋 Welcome to our store. Yes, the Black Wrap Dress is available — we have 8 units in stock! ✅ It comes in: XS, S, M, L, XL. Would you like to place an order? 😊	\N	\N	\N	\N	\N	\N	2026-06-02 07:07:57.014833	\N
33	11	10	instagram_dm	inbound	\N	hello? anyone there?	\N	\N	\N	\N	\N	\N	2026-06-02 07:10:16.737038	\N
34	13	12	instagram_dm	inbound	\N	Do you have wedding dresses?	stock_inquiry|product_inquiry	\N	\N	\N	\N	\N	2026-06-03 08:16:34.477798	\N
35	13	12	instagram_dm	outbound	ai	Hi! 💍 We have a dedicated bridal collection — check it out here: shopzetu.com/collections/bridal	\N	\N	\N	\N	\N	\N	2026-06-03 08:16:34.579255	\N
41	18	17	instagram_dm	inbound	\N	I want a refund this is broken!	greeting|complaint	\N	\N	\N	\N	\N	2026-06-04 10:35:33.915791	\N
42	18	17	instagram_dm	outbound	ai	Thanks for reaching out — I'm connecting you with a member of our team who'll get back to you shortly. We appreciate your patience.	\N	\N	\N	\N	\N	\N	2026-06-04 10:35:34.22835	\N
\.


--
-- TOC entry 5175 (class 0 OID 16474)
-- Dependencies: 226
-- Data for Name: products_cache; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.products_cache (id, shopify_product_id, name, description, price, variants, images, tags, cached_at) FROM stdin;
\.


--
-- TOC entry 5177 (class 0 OID 16492)
-- Dependencies: 228
-- Data for Name: stock_cache; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.stock_cache (id, product_key, quantity, unit, warehouse, cached_at) FROM stdin;
\.


--
-- TOC entry 5169 (class 0 OID 16386)
-- Dependencies: 220
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.users (id, external_id, channel, name, avatar_url, is_human_handled, ai_disabled, created_at, updated_at) FROM stdin;
1	seed:amina_ke	instagram_dm	@amina_ke	\N	f	f	2026-05-28 16:18:54.007103	2026-05-28 16:18:54.007103
2	seed:254712345678	whatsapp	+254712345678	\N	f	f	2026-05-28 16:18:54.007103	2026-05-28 16:18:54.007103
3	seed:beauty_nairobi	instagram_comment	@beauty_nairobi	\N	f	f	2026-05-28 16:18:54.007103	2026-05-28 16:18:54.007103
4	seed:fatuma_style	instagram_dm	@fatuma.style	\N	t	t	2026-05-28 16:18:54.007103	2026-05-28 16:18:54.007103
5	seed:254798001122	whatsapp	+254798001122	\N	f	f	2026-05-28 16:18:54.007103	2026-05-28 16:18:54.007103
6	seed:david_ochieng_fb	facebook_dm	David Ochieng	\N	f	f	2026-05-28 16:18:54.007103	2026-05-28 16:18:54.007103
7	seed:wanjiru_kamau_fb	facebook_comment	Wanjiru Kamau	\N	f	f	2026-05-28 16:18:54.007103	2026-05-28 16:18:54.007103
8	seed:tiktok_fashionista	tiktok_dm	@tiktok_fashionista	\N	f	f	2026-05-28 16:18:54.007103	2026-05-28 16:18:54.007103
10	test_user_keyword_1	instagram_dm	\N	\N	f	f	2026-06-02 06:57:11.988639	2026-06-02 06:57:11.988639
11	test_user_normal_1	instagram_dm	\N	\N	f	f	2026-06-02 07:07:56.936295	2026-06-02 07:07:56.936295
12	test_template_user_1	instagram_dm	\N	\N	f	f	2026-06-03 08:16:34.450163	2026-06-03 08:16:34.450163
17	auto_assign_test_user	instagram_dm	\N	\N	f	f	2026-06-04 10:35:33.901936	2026-06-04 10:35:33.902943
\.


--
-- TOC entry 5206 (class 0 OID 0)
-- Dependencies: 229
-- Name: ai_settings_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.ai_settings_id_seq', 1, false);


--
-- TOC entry 5207 (class 0 OID 0)
-- Dependencies: 237
-- Name: audit_logs_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.audit_logs_id_seq', 177, true);


--
-- TOC entry 5208 (class 0 OID 0)
-- Dependencies: 235
-- Name: auth_users_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.auth_users_id_seq', 7, true);


--
-- TOC entry 5209 (class 0 OID 0)
-- Dependencies: 231
-- Name: automation_rules_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.automation_rules_id_seq', 7, true);


--
-- TOC entry 5210 (class 0 OID 0)
-- Dependencies: 239
-- Name: channels_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.channels_id_seq', 7, true);


--
-- TOC entry 5211 (class 0 OID 0)
-- Dependencies: 221
-- Name: conversations_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.conversations_id_seq', 18, true);


--
-- TOC entry 5212 (class 0 OID 0)
-- Dependencies: 233
-- Name: logs_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.logs_id_seq', 64, true);


--
-- TOC entry 5213 (class 0 OID 0)
-- Dependencies: 223
-- Name: messages_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.messages_id_seq', 42, true);


--
-- TOC entry 5214 (class 0 OID 0)
-- Dependencies: 225
-- Name: products_cache_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.products_cache_id_seq', 577, true);


--
-- TOC entry 5215 (class 0 OID 0)
-- Dependencies: 227
-- Name: stock_cache_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.stock_cache_id_seq', 1, false);


--
-- TOC entry 5216 (class 0 OID 0)
-- Dependencies: 219
-- Name: users_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.users_id_seq', 17, true);


--
-- TOC entry 4983 (class 2606 OID 16532)
-- Name: ai_settings ai_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.ai_settings
    ADD CONSTRAINT ai_settings_pkey PRIMARY KEY (id);


--
-- TOC entry 5002 (class 2606 OID 24615)
-- Name: audit_logs audit_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.audit_logs
    ADD CONSTRAINT audit_logs_pkey PRIMARY KEY (id);


--
-- TOC entry 4995 (class 2606 OID 24598)
-- Name: auth_users auth_users_email_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.auth_users
    ADD CONSTRAINT auth_users_email_key UNIQUE (email);


--
-- TOC entry 4997 (class 2606 OID 24596)
-- Name: auth_users auth_users_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.auth_users
    ADD CONSTRAINT auth_users_pkey PRIMARY KEY (id);


--
-- TOC entry 4985 (class 2606 OID 16553)
-- Name: automation_rules automation_rules_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.automation_rules
    ADD CONSTRAINT automation_rules_pkey PRIMARY KEY (id);


--
-- TOC entry 5007 (class 2606 OID 24642)
-- Name: channels channels_channel_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.channels
    ADD CONSTRAINT channels_channel_key UNIQUE (channel);


--
-- TOC entry 5009 (class 2606 OID 24640)
-- Name: channels channels_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.channels
    ADD CONSTRAINT channels_pkey PRIMARY KEY (id);


--
-- TOC entry 4956 (class 2606 OID 16429)
-- Name: conversations conversations_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.conversations
    ADD CONSTRAINT conversations_pkey PRIMARY KEY (id);


--
-- TOC entry 4993 (class 2606 OID 16570)
-- Name: logs logs_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.logs
    ADD CONSTRAINT logs_pkey PRIMARY KEY (id);


--
-- TOC entry 4968 (class 2606 OID 16456)
-- Name: messages messages_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT messages_pkey PRIMARY KEY (id);


--
-- TOC entry 4970 (class 2606 OID 16458)
-- Name: messages messages_platform_message_id_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT messages_platform_message_id_key UNIQUE (platform_message_id);


--
-- TOC entry 4974 (class 2606 OID 16486)
-- Name: products_cache products_cache_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.products_cache
    ADD CONSTRAINT products_cache_pkey PRIMARY KEY (id);


--
-- TOC entry 4976 (class 2606 OID 16488)
-- Name: products_cache products_cache_shopify_product_id_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.products_cache
    ADD CONSTRAINT products_cache_shopify_product_id_key UNIQUE (shopify_product_id);


--
-- TOC entry 4979 (class 2606 OID 16504)
-- Name: stock_cache stock_cache_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.stock_cache
    ADD CONSTRAINT stock_cache_pkey PRIMARY KEY (id);


--
-- TOC entry 4981 (class 2606 OID 16506)
-- Name: stock_cache stock_cache_product_key_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.stock_cache
    ADD CONSTRAINT stock_cache_product_key_key UNIQUE (product_key);


--
-- TOC entry 4952 (class 2606 OID 16406)
-- Name: users uq_user_external_channel; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT uq_user_external_channel UNIQUE (external_id, channel);


--
-- TOC entry 4954 (class 2606 OID 16404)
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- TOC entry 5003 (class 1259 OID 24622)
-- Name: idx_audit_logs_action; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_audit_logs_action ON public.audit_logs USING btree (action);


--
-- TOC entry 5004 (class 1259 OID 24623)
-- Name: idx_audit_logs_created_at; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_audit_logs_created_at ON public.audit_logs USING btree (created_at DESC);


--
-- TOC entry 5005 (class 1259 OID 24621)
-- Name: idx_audit_logs_user_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_audit_logs_user_id ON public.audit_logs USING btree (user_id);


--
-- TOC entry 4998 (class 1259 OID 24599)
-- Name: idx_auth_users_email; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_auth_users_email ON public.auth_users USING btree (email);


--
-- TOC entry 4999 (class 1259 OID 24600)
-- Name: idx_auth_users_role; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_auth_users_role ON public.auth_users USING btree (role);


--
-- TOC entry 5000 (class 1259 OID 24601)
-- Name: idx_auth_users_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_auth_users_status ON public.auth_users USING btree (status);


--
-- TOC entry 4986 (class 1259 OID 16554)
-- Name: idx_automation_rules_enabled; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_automation_rules_enabled ON public.automation_rules USING btree (enabled);


--
-- TOC entry 4987 (class 1259 OID 16555)
-- Name: idx_automation_rules_sort_order; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_automation_rules_sort_order ON public.automation_rules USING btree (sort_order);


--
-- TOC entry 5010 (class 1259 OID 24643)
-- Name: idx_channels_channel; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_channels_channel ON public.channels USING btree (channel);


--
-- TOC entry 5011 (class 1259 OID 24644)
-- Name: idx_channels_enabled; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_channels_enabled ON public.channels USING btree (enabled);


--
-- TOC entry 4957 (class 1259 OID 32832)
-- Name: idx_conversations_assigned_to; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_conversations_assigned_to ON public.conversations USING btree (assigned_to);


--
-- TOC entry 4958 (class 1259 OID 16436)
-- Name: idx_conversations_channel; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_conversations_channel ON public.conversations USING btree (channel);


--
-- TOC entry 4959 (class 1259 OID 16437)
-- Name: idx_conversations_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_conversations_status ON public.conversations USING btree (status);


--
-- TOC entry 4960 (class 1259 OID 16438)
-- Name: idx_conversations_updated; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_conversations_updated ON public.conversations USING btree (updated_at DESC);


--
-- TOC entry 4961 (class 1259 OID 16435)
-- Name: idx_conversations_user_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_conversations_user_id ON public.conversations USING btree (user_id);


--
-- TOC entry 4988 (class 1259 OID 16579)
-- Name: idx_logs_conversation; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_logs_conversation ON public.logs USING btree (conversation_id);


--
-- TOC entry 4989 (class 1259 OID 16578)
-- Name: idx_logs_created_at; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_logs_created_at ON public.logs USING btree (created_at DESC);


--
-- TOC entry 4990 (class 1259 OID 16576)
-- Name: idx_logs_level; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_logs_level ON public.logs USING btree (level);


--
-- TOC entry 4991 (class 1259 OID 16577)
-- Name: idx_logs_source; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_logs_source ON public.logs USING btree (source);


--
-- TOC entry 4962 (class 1259 OID 16469)
-- Name: idx_messages_conversation_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_messages_conversation_id ON public.messages USING btree (conversation_id);


--
-- TOC entry 4963 (class 1259 OID 16471)
-- Name: idx_messages_created_at; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_messages_created_at ON public.messages USING btree (created_at DESC);


--
-- TOC entry 4964 (class 1259 OID 16472)
-- Name: idx_messages_intent; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_messages_intent ON public.messages USING btree (intent);


--
-- TOC entry 4965 (class 1259 OID 32821)
-- Name: idx_messages_sender_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_messages_sender_id ON public.messages USING btree (sender_id);


--
-- TOC entry 4966 (class 1259 OID 16470)
-- Name: idx_messages_user_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_messages_user_id ON public.messages USING btree (user_id);


--
-- TOC entry 4971 (class 1259 OID 16490)
-- Name: idx_products_cache_cached_at; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_products_cache_cached_at ON public.products_cache USING btree (cached_at);


--
-- TOC entry 4972 (class 1259 OID 16489)
-- Name: idx_products_cache_name; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_products_cache_name ON public.products_cache USING gin (to_tsvector('english'::regconfig, (name)::text));


--
-- TOC entry 4977 (class 1259 OID 16507)
-- Name: idx_stock_cache_cached_at; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_stock_cache_cached_at ON public.stock_cache USING btree (cached_at);


--
-- TOC entry 4950 (class 1259 OID 16407)
-- Name: idx_users_channel; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_users_channel ON public.users USING btree (channel);


--
-- TOC entry 5020 (class 2606 OID 24616)
-- Name: audit_logs audit_logs_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.audit_logs
    ADD CONSTRAINT audit_logs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.auth_users(id) ON DELETE CASCADE;


--
-- TOC entry 5012 (class 2606 OID 32827)
-- Name: conversations conversations_assigned_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.conversations
    ADD CONSTRAINT conversations_assigned_by_fkey FOREIGN KEY (assigned_by) REFERENCES public.auth_users(id) ON DELETE SET NULL;


--
-- TOC entry 5013 (class 2606 OID 32822)
-- Name: conversations conversations_assigned_to_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.conversations
    ADD CONSTRAINT conversations_assigned_to_fkey FOREIGN KEY (assigned_to) REFERENCES public.auth_users(id) ON DELETE SET NULL;


--
-- TOC entry 5014 (class 2606 OID 32833)
-- Name: conversations conversations_resolved_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.conversations
    ADD CONSTRAINT conversations_resolved_by_fkey FOREIGN KEY (resolved_by) REFERENCES public.auth_users(id) ON DELETE SET NULL;


--
-- TOC entry 5015 (class 2606 OID 16430)
-- Name: conversations conversations_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.conversations
    ADD CONSTRAINT conversations_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- TOC entry 5019 (class 2606 OID 16571)
-- Name: logs logs_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.logs
    ADD CONSTRAINT logs_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.conversations(id) ON DELETE SET NULL;


--
-- TOC entry 5016 (class 2606 OID 16459)
-- Name: messages messages_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT messages_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.conversations(id) ON DELETE CASCADE;


--
-- TOC entry 5017 (class 2606 OID 32816)
-- Name: messages messages_sender_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT messages_sender_id_fkey FOREIGN KEY (sender_id) REFERENCES public.auth_users(id) ON DELETE SET NULL;


--
-- TOC entry 5018 (class 2606 OID 16464)
-- Name: messages messages_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT messages_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


-- Completed on 2026-06-04 15:56:02

--
-- PostgreSQL database dump complete
--

\unrestrict K3tb1eKTtNecXgWejZ2LXcHYnyIiWP8qseVngnxZyUBmxrCMqaYYzxtMI7OMvHv

