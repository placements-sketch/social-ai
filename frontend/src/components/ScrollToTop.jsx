import { useState, useEffect } from 'react'
import { ArrowUp } from 'lucide-react'
import { ModalPortal } from '../context/ModalPortal'

export default function ScrollToTop() {
  const [isVisible, setIsVisible] = useState(false)
  const [chatOpen, setChatOpen] = useState(false)

  const scrollToTop = () => {
    const mainElement = document.querySelector('main')
    if (mainElement) {
      mainElement.scrollTo({ top: 0, behavior: 'smooth' })
    } else {
      window.scrollTo({ top: 0, behavior: 'smooth' })
    }
  }

  useEffect(() => {
    const mainElement = document.querySelector('main')
    const handleScroll = () => {
      const scrollTop = mainElement ? mainElement.scrollTop : window.scrollY
      setIsVisible(scrollTop > 300)
    }
    if (mainElement) {
      mainElement.addEventListener('scroll', handleScroll)
      return () => mainElement.removeEventListener('scroll', handleScroll)
    } else {
      window.addEventListener('scroll', handleScroll)
      return () => window.removeEventListener('scroll', handleScroll)
    }
  }, [])

  useEffect(() => {
    const onChatToggle = (e) => setChatOpen(!!e.detail?.open)
    window.addEventListener('chat-panel-toggle', onChatToggle)
    return () => window.removeEventListener('chat-panel-toggle', onChatToggle)
  }, [])

  if (!isVisible || chatOpen) return null

  return (
    <ModalPortal>
      <button
        onClick={scrollToTop}
        /* Bottom of the fixed-corner ladder, top slot:
             Ask the docs   bottom 20   (h 40)  ->  20-60
             Customer AI    bottom 72   (h 56)  ->  72-128
             Scroll to top  bottom 140  (h 40)  -> 140-180
           12px of clear space between each. This was bottom-24 (96px), which
           sat inside the customer assistant's box and over the pagination. */
        className="fixed right-6 w-10 h-10 rounded-full bg-black text-white flex items-center justify-center transition-all duration-200 hover:bg-gray-900 shadow-lg z-50 hover:scale-110"
        style={{ bottom: 140 }}
        title="Scroll to top"
        aria-label="Scroll to top"
      >
        <ArrowUp size={18} />
      </button>
    </ModalPortal>
  )
}