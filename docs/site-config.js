/* Все ссылки сайта — в одном месте. Меняйте здесь: подвал, блок «Мы в соцсетях» и ссылка на бота подхватят сами.
   Клуб вымышленный, поэтому Instagram / VK / TikTok / Discord — заглушки (ведут на главные страницы сетей): замените на свои.
   Telegram ведёт на настоящего бота CyberBounty; тот же бот открывает mini app с бронью. */
window.CB_LINKS = {
  bot: "cyberbounty_bot",                                  // username бота в Telegram (без @)
  botUrl: "https://t.me/cyberbounty_bot",                  // бот + mini app
  socials: [
    { id: "telegram",  label: "Telegram",  href: "https://t.me/cyberbounty_bot" },
    { id: "instagram", label: "Instagram", href: "https://www.instagram.com/" },
    { id: "vk",        label: "VK",        href: "https://vk.com/" },
    { id: "tiktok",    label: "TikTok",    href: "https://www.tiktok.com/" },
    { id: "discord",   label: "Discord",   href: "https://discord.com/" }
  ]
};
