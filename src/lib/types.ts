export type Identity = {
  provider: 'twitch' | 'discord' | 'google';
  display_name: string;
  avatar_url?: string;
};

export type Account = {
  authenticated: boolean;
  is_admin: boolean;
  request_name?: string;
  identities: Identity[];
};

export type Song = {
  id: string;
  title: string;
  parenthetical: string;
  tags: string[];
  is_new: boolean;
  tag_points: number;
  play_count: number;
  last_played: string | null;
};

export type Catalog = {
  songs: Song[];
  tags: { name: string; points: number; color?: string }[];
};

export type QueueItem = {
  title: string;
  user: string;
  can_remove?: boolean;
};

export type QueueState = {
  queue: QueueItem[];
  connected: boolean;
  queue_open: boolean | null;
};

export type Settings = {
  song_text: string;
  new_play_threshold: number;
  new_min_days: number;
  recently_graduated_days: number;
  last_played_history_limit: number;
  default_artist: string;
  queue_websocket_url: string;
  queue_group: string;
};

export type SongGroup = {
  id?: string;
  display_name: string;
  members: string[];
};
