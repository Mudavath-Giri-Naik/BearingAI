import type { Metadata } from 'next';
import './globals.css';
export const metadata:Metadata={title:'BearingAI | Precision Bearing Intelligence',description:'Industrial signal analysis, with independently versioned NBC and TIMKEN models.'};
export default function RootLayout({children}:{children:React.ReactNode}){return <html lang="en"><body>{children}</body></html>}
