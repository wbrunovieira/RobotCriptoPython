"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const tabs = [
  { label: "Bot BRL", href: "/" },
  { label: "Bot Meme", href: "/meme" },
];

export default function TabsNav() {
  const pathname = usePathname();
  return (
    <nav className="bg-gray-900 border-b border-gray-800 px-4">
      <div className="max-w-6xl mx-auto flex gap-1">
        {tabs.map((tab) => {
          const active = pathname === tab.href;
          return (
            <Link
              key={tab.href}
              href={tab.href}
              className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                active
                  ? "border-white text-white"
                  : "border-transparent text-gray-400 hover:text-gray-200"
              }`}
            >
              {tab.label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
