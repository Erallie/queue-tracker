import type { Account, Catalog, Settings, SongGroup } from './types';

export const demoAccount: Account = {
  authenticated: false,
  is_admin: false,
  identities: []
};

export const demoCatalog: Catalog = {
  tags: [
    { name: 'New', points: 100, color: '#d33355' },
    { name: 'Musical', points: 20, color: '#7551c9' },
    { name: 'Disney', points: 12, color: '#14794d' },
    { name: 'Duet', points: 8, color: '#c1732c' },
    { name: 'Jazz', points: 5, color: '#276a89' }
  ],
  songs: [
    { id: 'dangerous', title: 'Dangerous to Dream', parenthetical: 'Frozen', tags: ['New', 'Musical', 'Disney'], is_new: true, tag_points: 132, play_count: 2, last_played: '2026-08-31' },
    { id: 'still-hurting', title: 'Still Hurting', parenthetical: 'The Last Five Years', tags: ['New', 'Musical'], is_new: true, tag_points: 120, play_count: 0, last_played: null },
    { id: 'green', title: "Somewhere That's Green", parenthetical: 'Little Shop of Horrors', tags: ['New', 'Musical'], is_new: true, tag_points: 120, play_count: 0, last_played: null },
    { id: 'fly-me', title: 'Fly Me to the Moon', parenthetical: 'Frank Sinatra', tags: ['New', 'Jazz'], is_new: true, tag_points: 105, play_count: 1, last_played: '2026-08-29' },
    { id: 'rainbow', title: 'Somewhere Over the Rainbow', parenthetical: 'Judy Garland', tags: ['Jazz'], is_new: false, tag_points: 5, play_count: 3, last_played: '2026-08-21' },
    { id: 'crossing', title: 'Crossing the Line', parenthetical: "Rapunzel's Tangled Adventure", tags: ['Musical', 'Disney'], is_new: false, tag_points: 32, play_count: 4, last_played: '2026-08-14' },
    { id: 'prayer', title: 'The Prayer', parenthetical: 'Quest for Camelot', tags: ['Duet'], is_new: false, tag_points: 8, play_count: 8, last_played: '2026-07-30' }
  ]
};

export const demoSettings: Settings = {
  song_text: `# Originals\nI'm Waiting For My Prince To Come\nIn the Darkness\nOn This Holy Evening\nPandemonium\nWind and Water\nYou Are God\n\n# Musicals/Film\n## F:\nDangerous to Dream (Frozen) [New]\nFor the First Time in Forever (Frozen)\nLet It Go (Frozen)\n\n## L:\nStill Hurting (The Last Five Years) [New]\nSomewhere That's Green (Little Shop of Horrors) [New]\n\n# Jazz/Oldies\nSomewhere Over the Rainbow (Judy Garland)\nFly Me to the Moon (Frank Sinatra) [New]`,
  new_play_threshold: 2,
  new_min_days: 14,
  recently_graduated_days: 7,
  last_played_history_limit: 10,
  default_artist: 'Erallie',
  queue_websocket_url: 'wss://sikorsky.mustardmine.com/ws',
  queue_group: '#275206561'
};

export const demoGroups: SongGroup[] = [
  { id: 'rainbow', display_name: 'Somewhere Over the Rainbow (Judy Garland)', members: ['Somewhere Over the Rainbow - Jazz Cover (The Wizard of Oz)', 'Somewhere Over the Rainbow (Judy Garland)'] },
  { id: 'crossing', display_name: "Crossing the Line (Rapunzel's Tangled Adventure)", members: ["Crossing the Line (Rapunzel's Tangled Adventure)", 'Crossing the Line (Tangled the Series)'] }
];
