import { useState, useEffect } from 'react'
import { ArrowUp } from 'lucide-react'
import { ModalPortal } from '../context/ModalPortal'

export default function ScrollToTop() {
  const [isVisible, setIsVisible] = useState(false)

  const scrollToTop = () => {
    const mainElement = document.querySelector('main')
    if (mainElement) {
      mainElement.scrollTo({
        top: 0,
        behavior: 'smooth',
      })
    } else {
      window.scrollTo({
        top: 0,
        behavior: 'smooth',
      })
    }
  }

  useEffect(() => {
    const mainElement = document.querySelector('main')
    
    const handleScroll = () => {
      const scrollContainer = mainElement || window
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

  if (!isVisible) return null

  return (
    <ModalPortal>
      <button
        onClick={scrollToTop}
        className="fixed bottom-6 right-6 w-10 h-10 rounded-full bg-black text-white flex items-center justify-center transition-all duration-200 hover:bg-gray-900 shadow-lg z-50 hover:scale-110"
        title="Scroll to top"
        aria-label="Scroll to top"
      >
        <ArrowUp size={18} />
      </button>
    </ModalPortal>
  )
}


