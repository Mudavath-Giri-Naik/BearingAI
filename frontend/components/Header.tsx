'use client';
import Link from 'next/link';
import {Activity,ArrowUpRight,Shield} from 'lucide-react';
export function Header(){return <header className="topbar"><Link className="brand" href="/"><span className="brand-icon"><Activity size={20}/></span><span>Bearing<span className="accent-text">AI</span></span><span className="brand-sub">/ PULSE SYSTEMS</span></Link><nav><Link href="/">Overview</Link><Link href="/analyze">Analyze</Link><Link href="/studio" className="nav-studio"><Shield size={15}/> Studio <ArrowUpRight size={14}/></Link></nav></header>}
