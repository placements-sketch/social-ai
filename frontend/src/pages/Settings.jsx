import { useState } from 'react'
import { Save, Eye, EyeOff } from 'lucide-react'

const Section = ({ title, children }) => (
  <div className="card p-5 space-y-4">
    <h2 className="text-sm font-bold text-gray-900">{title}</h2>
    {children}
  </div>
)

const Field = ({ label, hint, children }) => (
  <div>
    <label className="block text-xs font-bold text-gray-600 mb-1.5">{label}</label>
    {hint && <p className="text-xs text-gray-400 mb-1.5">{hint}</p>}
    {children}
  </div>
)

function SecretInput({ placeholder, value }) {
  const [show, setShow] = useState(false)
  return (
    <div className="relative">
      <input
        type={show ? 'text' : 'password'}
        defaultValue={value}
        placeholder={placeholder}
        className="input w-full pr-9 font-mono text-xs"
      />
      <button
        onClick={() => setShow(!show)}
        className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
      >
        {show ? <EyeOff size={13} /> : <Eye size={13} />}
      </button>
    </div>
  )
}

export default function Settings() {
  return (
    <div className="space-y-6 w-full max-w-4xl mx-auto">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Settings</h1>
            <p className="text-sm text-gray-500 mt-0.5">API keys, webhooks, and system configuration</p>
          </div>
          <span className="px-2 py-0.5 rounded-md text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200">
            Preview
          </span>
        </div>
        <button
          disabled
          className="flex items-center gap-2 px-3 py-2 rounded-lg bg-gray-100 text-gray-400 text-xs font-semibold cursor-not-allowed"
          title="Settings management is in preview — values managed via environment variables for now"
        >
          <Save size={14} /> Save All
        </button>
      </div>

      <div className="bg-amber-50 border border-amber-200 rounded-lg p-4">
        <p className="text-sm font-semibold text-amber-900 mb-1">Preview interface</p>
        <p className="text-xs text-amber-800 leading-relaxed">
          This page is a visual preview of upcoming settings management. For now, all API keys, tokens, and webhook URLs
          are managed via environment variables on the backend. Use the Channels page to verify Meta/Instagram credentials
          are connected, and Render's dashboard to update environment variables.
        </p>
      </div>

      <Section title="AI & LLM Configuration">
        <div className="bg-blue-50 border border-blue-200 rounded-lg px-3 py-2.5">
          <p className="text-xs text-blue-700 font-semibold">
            Claude API is used for all AI-powered customer responses and intent detection.
          </p>
        </div>
        <Field label="Claude API Key">
          <SecretInput placeholder="sk-…" value="sk-••••••••••••••••••••••••" />
        </Field>
      </Section>

      <Section title="Meta Platforms (Instagram, Facebook, WhatsApp)">
        <div className="bg-blue-50 border border-blue-200 rounded-lg px-3 py-2.5">
          <p className="text-xs text-blue-700 font-semibold">
            Meta Graph API credentials for Instagram DMs, Comments, Facebook Messenger, and WhatsApp.
          </p>
        </div>
        <Field label="Meta Page Access Token">
          <SecretInput placeholder="EAABs…" value="EAABs••••••••••••••••••••" />
        </Field>
        <Field label="Meta Verify Token" hint="Must match what you set in Meta Developer Console">
          <input className="input w-full font-mono text-xs" defaultValue="my-verify-token-2024" />
        </Field>
      </Section>

      <Section title="TikTok Configuration">
        <div className="bg-amber-50 border border-amber-200 rounded-lg px-3 py-2.5">
          <p className="text-xs text-amber-700 font-semibold">
            TikTok has separate API credentials from Meta. Get these from TikTok Developer Portal.
          </p>
        </div>
        <Field label="TikTok Client Key">
          <SecretInput placeholder="client_key_…" value="client_key_••••••••••••••••" />
        </Field>
        <Field label="TikTok Client Secret">
          <SecretInput placeholder="client_secret_…" value="client_secret_••••••••••••••••" />
        </Field>
        <Field label="TikTok Access Token">
          <SecretInput placeholder="act_…" value="act_••••••••••••••••••••••••" />
        </Field>
        <Field label="TikTok Verify Token" hint="For webhook signature verification">
          <input className="input w-full font-mono text-xs" defaultValue="tiktok-verify-token-2024" />
        </Field>
      </Section>

      <Section title="Shopify Configuration">
        <div className="bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2.5">
          <p className="text-xs text-emerald-700 font-semibold">
            Shopify is the source of truth for all product inventory and pricing data.
          </p>
        </div>
        <Field label="Shopify Store URL" hint="e.g., yourstore.myshopify.com">
          <input className="input w-full text-xs" defaultValue="yourstore.myshopify.com" />
        </Field>
        <Field label="Shopify Access Token">
          <SecretInput placeholder="shpat_…" value="shpat_••••••••••••••••" />
        </Field>
      </Section>

      <Section title="Webhook Configuration">
        <Field label="Base URL" hint="Your public domain (used to display webhook URLs)">
          <input className="input w-full text-xs" defaultValue="https://yourdomain.com" />
        </Field>
        <Field label="Instagram Webhook URL">
          <input className="input w-full text-xs font-mono" defaultValue="https://yourdomain.com/webhook/instagram" />
        </Field>
        <Field label="WhatsApp Webhook URL">
          <input className="input w-full text-xs font-mono" defaultValue="https://yourdomain.com/webhook/whatsapp" />
        </Field>
        <Field label="Facebook Webhook URL">
          <input className="input w-full text-xs font-mono" defaultValue="https://yourdomain.com/webhook/facebook" />
        </Field>
        <Field label="Facebook Comments Webhook URL">
          <input className="input w-full text-xs font-mono" defaultValue="https://yourdomain.com/webhook/facebook/comments" />
        </Field>
        <Field label="TikTok Webhook URL">
          <input className="input w-full text-xs font-mono" defaultValue="https://yourdomain.com/webhook/tiktok" />
        </Field>
      </Section>

      <Section title="Business Hours">
        <div className="bg-brand-50 border border-brand-100 rounded-lg px-3 py-2.5">
          <p className="text-xs text-brand-700 font-semibold">
            Your AI replies 24/7 regardless of these settings. Business hours only affect human escalation routing.
          </p>
        </div>
        <div className="grid grid-cols-2 gap-4">
          <Field label="Opening Time">
            <input type="time" className="input w-full text-xs" defaultValue="08:00" />
          </Field>
          <Field label="Closing Time">
            <input type="time" className="input w-full text-xs" defaultValue="20:00" />
          </Field>
        </div>
        <Field label="Timezone">
          <select className="input w-full text-xs">
            <option value="Africa/Nairobi">Africa/Nairobi (EAT, UTC+3)</option>
            <option value="UTC">UTC</option>
            <option value="Africa/Lagos">Africa/Lagos (WAT, UTC+1)</option>
          </select>
        </Field>
      </Section>

      <Section title="Fallback Messages">
        <Field label="AI Failure Fallback" hint="Shown when Claude API call fails">
          <textarea className="input w-full resize-none text-xs" rows={2}
            defaultValue="Thanks for reaching out! We're experiencing a brief delay. Our team will respond shortly. 🙏" />
        </Field>
        <Field label="Out-of-Stock Message">
          <textarea className="input w-full resize-none text-xs" rows={2}
            defaultValue="This item is currently out of stock. Would you like to be notified when it's back? 📦" />
        </Field>
      </Section>

      <Section title="Rate Limits">
        <div className="grid grid-cols-2 gap-4">
          <Field label="Max replies per user / hour">
            <input type="number" className="input w-full text-xs" defaultValue={20} />
          </Field>
          <Field label="Claude max tokens per reply">
            <input type="number" className="input w-full text-xs" defaultValue={200} />
          </Field>
        </div>
      </Section>
    </div>
  )
}
