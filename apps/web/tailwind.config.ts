import type { Config } from "tailwindcss";
import animate from "tailwindcss-animate";

const config: Config = {
  darkMode: ["class"],
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
  	extend: {
  		colors: {
  			border: 'hsl(var(--border))',
  			input: 'hsl(var(--input))',
  			ring: 'hsl(var(--ring))',
  			background: 'hsl(var(--background))',
  			foreground: 'hsl(var(--foreground))',
  			primary: {
  				DEFAULT: 'hsl(var(--primary))',
  				foreground: 'hsl(var(--primary-foreground))'
  			},
  			secondary: {
  				DEFAULT: 'hsl(var(--secondary))',
  				foreground: 'hsl(var(--secondary-foreground))'
  			},
  			destructive: {
  				DEFAULT: 'hsl(var(--destructive))',
  				foreground: 'hsl(var(--destructive-foreground))'
  			},
  			muted: {
  				DEFAULT: 'hsl(var(--muted))',
  				foreground: 'hsl(var(--muted-foreground))'
  			},
  			accent: {
  				DEFAULT: 'hsl(var(--accent))',
  				foreground: 'hsl(var(--accent-foreground))'
  			},
  			popover: {
  				DEFAULT: 'hsl(var(--popover))',
  				foreground: 'hsl(var(--popover-foreground))'
  			},
  			card: {
  				DEFAULT: 'hsl(var(--card))',
  				foreground: 'hsl(var(--card-foreground))'
  			},
  			profit: 'hsl(var(--profit))',
  			loss: 'hsl(var(--loss))',
  			warning: 'hsl(var(--warning))',
  			info: 'hsl(var(--info))',
  			subtle: 'hsl(var(--subtle-foreground))',
			'border-strong': 'hsl(var(--border-strong))',
			execution: {
				paper: 'hsl(var(--execution-paper))',
				testnet: 'hsl(var(--execution-testnet))',
				live: 'hsl(var(--execution-live))',
				blocked: 'hsl(var(--execution-blocked))',
			},
			status: {
				online: 'hsl(var(--status-online))',
				offline: 'hsl(var(--status-offline))',
				stale: 'hsl(var(--status-stale))',
			},
  			ai: 'hsl(var(--ai))',
  			electric: 'hsl(var(--electric))',
  			brand: 'hsl(var(--brand))',
  			'paper-mode': 'hsl(var(--paper-mode))',
  			'live-mode': 'hsl(var(--live-mode))',
  			halted: 'hsl(var(--halted))',
  			'stale-data': 'hsl(var(--stale-data))',
  			disabled: 'hsl(var(--disabled))',
  			chart: {
  				'1': 'hsl(var(--chart-1))',
  				'2': 'hsl(var(--chart-2))',
  				'3': 'hsl(var(--chart-3))',
  				'4': 'hsl(var(--chart-4))',
  				'5': 'hsl(var(--chart-5))',
  			},
  			copper: {
  				DEFAULT: 'hsl(var(--cn-copper))',
  				soft: 'hsl(var(--cn-copper-soft))',
  			},
  			panel: {
  				DEFAULT: 'hsl(var(--cn-panel))',
  				elevated: 'hsl(var(--cn-panel-elevated))',
  			},
  			sidebar: {
  				DEFAULT: 'hsl(var(--sidebar-background))',
  				foreground: 'hsl(var(--sidebar-foreground))',
  				primary: 'hsl(var(--sidebar-primary))',
  				'primary-foreground': 'hsl(var(--sidebar-primary-foreground))',
  				accent: 'hsl(var(--sidebar-accent))',
  				'accent-foreground': 'hsl(var(--sidebar-accent-foreground))',
  				border: 'hsl(var(--sidebar-border))',
  				ring: 'hsl(var(--sidebar-ring))'
  			}
  		},
  		borderRadius: {
  			lg: 'var(--radius)',
  			md: 'calc(var(--radius) - 2px)',
  			sm: 'calc(var(--radius) - 4px)'
  		},
  		fontFamily: {
  			sans: [
  				'var(--font-sans)',
  				'Segoe UI',
  				'sans-serif'
  			],
  			display: [
  				'var(--font-display)',
  				'Georgia',
  				'serif'
  			],
  			mono: [
  				'var(--font-mono)',
  				'ui-monospace',
  				'monospace'
  			]
  		},
		keyframes: {
			'border-beam': {
				'100%': {
					'offset-distance': '100%'
				}
			},
			'blur-fade': {
				from: {
					opacity: '0',
					filter: 'blur(6px)',
					transform: 'translateY(8px)'
				},
				to: {
					opacity: '1',
					filter: 'blur(0)',
					transform: 'translateY(0)'
				}
			},
			ripple: {
				'0%, 100%': {
					transform: 'translate(-50%, -50%) scale(1)'
				},
				'50%': {
					transform: 'translate(-50%, -50%) scale(0.92)'
				}
			},
			marquee: {
				from: {
					transform: 'translateX(0)'
				},
				to: {
					transform: 'translateX(calc(-100% - var(--gap)))'
				}
			},
			'marquee-vertical': {
				from: {
					transform: 'translateY(0)'
				},
				to: {
					transform: 'translateY(calc(-100% - var(--gap)))'
				}
			},
			'accordion-down': {
				from: { height: '0' },
				to: { height: 'var(--radix-collapsible-content-height)' },
			},
			'accordion-up': {
				from: { height: 'var(--radix-collapsible-content-height)' },
				to: { height: '0' },
			},
			'trace-shimmer': {
				'0%': { backgroundPosition: '100% 0' },
				'100%': { backgroundPosition: '0% 0' },
			},
			shimmer: {
				'0%, 90%, 100%': {
					'background-position': 'calc(-100% - var(--shimmer-width)) 0'
				},
				'30%, 60%': {
					'background-position': 'calc(100% + var(--shimmer-width)) 0'
				}
			},
  			meteor: {
  				'0%': {
  					transform: 'rotate(215deg) translateX(0)',
  					opacity: '1'
  				},
  				'70%': {
  					opacity: '1'
  				},
  				'100%': {
  					transform: 'rotate(215deg) translateX(-500px)',
  					opacity: '0'
  				}
  			},
  			'aurora-border': {
  				'0%, 100%': {
  					'background-position': '0% 50%'
  				},
  				'50%': {
  					'background-position': '100% 50%'
  				}
  			},
  			'shimmer-slide': {
  				to: {
  					transform: 'translate(calc(100cqw - 100%), 0)'
  				}
  			},
  			'spin-around': {
  				'0%': {
  					transform: 'translateZ(0) rotate(0)'
  				},
  				'15%, 35%': {
  					transform: 'translateZ(0) rotate(90deg)'
  				},
  				'65%, 85%': {
  					transform: 'translateZ(0) rotate(270deg)'
  				},
  				'100%': {
  					transform: 'translateZ(0) rotate(360deg)'
  				}
  			}
  		},
  		animation: {
  			'border-beam': 'border-beam calc(var(--duration)*1s) infinite linear',
  			'blur-fade': 'blur-fade 0.5s ease forwards',
  			ripple: 'ripple 2.4s ease calc(var(--i, 0) * 0.08s) infinite',
  			marquee: 'marquee var(--duration) linear infinite',
  			'marquee-vertical': 'marquee-vertical var(--duration) linear infinite',
  			'accordion-down': 'accordion-down 0.2s ease-out',
  			'accordion-up': 'accordion-up 0.2s ease-out',
  			'trace-shimmer': 'trace-shimmer 1.6s linear infinite',
  			shimmer: 'shimmer 8s infinite',
  			meteor: 'meteor 5s linear infinite',
  			'aurora-border': 'aurora-border 6s ease infinite',
  			'shimmer-slide': 'shimmer-slide var(--speed) ease-in-out infinite alternate',
  			'spin-around': 'spin-around calc(var(--speed) * 2) infinite linear'
  		}
  	}
  },
  plugins: [animate],
};

export default config;
