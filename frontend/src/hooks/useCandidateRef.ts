import { useCallback, useEffect, useState } from 'react'

// Who is consenting. Kept in this browser only - the API takes it per request.
export const CANDIDATE_STORAGE_KEY = 'hire.candidate_ref'

function read(): string {
  try {
    return window.localStorage.getItem(CANDIDATE_STORAGE_KEY) || ''
  } catch {
    return ''
  }
}

export function useCandidateRef(): [string, (value: string) => void] {
  const [candidateRef, setState] = useState<string>(read)

  // Keep the deck and the board in step when one of them changes the handle.
  useEffect(() => {
    function onStorage(event: StorageEvent) {
      if (event.key === CANDIDATE_STORAGE_KEY) setState(event.newValue || '')
    }
    window.addEventListener('storage', onStorage)
    return () => window.removeEventListener('storage', onStorage)
  }, [])

  const update = useCallback((value: string) => {
    setState(value)
    try {
      if (value) window.localStorage.setItem(CANDIDATE_STORAGE_KEY, value)
      else window.localStorage.removeItem(CANDIDATE_STORAGE_KEY)
    } catch {
      // Private browsing: the handle simply does not survive a reload.
    }
  }, [])

  return [candidateRef, update]
}
