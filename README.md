# Store Lists

A Home Assistant integration that puts the right shopping list on your phone when you stop at a
shop that serves it — without a zone for every shop. Stop for a few minutes at an IKEA, a
Leroy Merlin or a shopping centre, and the people you chose get a notification with what is
still on the matching to-do lists.

Where you are comes from your phones (the companion app); what is around comes from
**Google Places (New)**, asked only when someone has stopped away from home and one of the
lists has something on it.

## How it decides

1. A person's location stops changing for a few minutes (3 by default), away from home, within
   the hours you set (08:00–23:00 by default) and with a usable GPS fix.
2. If any configured list has open items, Places is asked what shops are within the radius
   (100 m by default).
3. Each list says which shops it is for:

   | Kind | Matches |
   |---|---|
   | Home & furniture | IKEA, Zara Home, JYSK, Espaço Casa, Maisons du Monde, Flying Tiger… and any shop whose main type is furniture or home goods (electronics chains excluded) |
   | DIY & hardware | Leroy Merlin, AKI, Bricomarché, Brico Dépôt, Maxmat, Bauhaus… and any home improvement or hardware shop |
   | Shopping centres | Shopping centres and department stores (El Corte Inglés) |
   | Only the keywords | Shops whose name contains one of your keywords |

   Every kind also takes extra keywords (`Primark, Decathlon`).
4. Inside a shopping centre the phone cannot tell one shop from the next, so one notification
   covers the centre: the shopping-centre list plus every other list with a shop inside, naming
   those shops. The centre's name comes from the busiest mall nearby, because Places tags some
   shops inside malls as malls themselves.
5. Supermarkets, hypermarkets and department stores never count as home or DIY shops on their
   type alone.

The notification shows up to five items per list and one button per list that opens it in the
app. Each person is told at most once a day per shop (or shopping centre).

## Setup

1. In Google Cloud, enable **Places API (New)** and create an API key restricted to it. A
   billing account is required; the monthly free tier covers personal use comfortably (one
   request per stop, two inside shopping centres). Capping the API at ~100 requests a day in
   *Quotas* keeps it free whatever happens.
2. Install through HACS (custom repository `lucasgiovanny/ha-store-lists`, category
   *Integration*) and restart.
3. *Settings → Devices & services → Add integration → Store Lists*: paste the key, pick the
   people to watch. Each person needs the companion app on their phone; the notify service is
   found through their device tracker.
4. *Configure → Add or change a list*: pick a to-do list and its kind. Timing, radius and the
   hours live under *Timing and radius*.

## What it gives you

| | |
|---|---|
| `sensor.store_lists_last_store_<person>` | The last shop each person stopped at, with the lists it served |
| `store_lists_match` event | Fired with the person, place, lists and message on every match |
| `store_lists.check` | Asks what is around a person (or any point) and returns the answer; notifies only with `notify: true` |
| Repair issue | Raised while Places is failing; whoever you chose also gets one phone notification a day |

```yaml
action: store_lists.check
data:
  person: person.me
  latitude: 38.8174
  longitude: -9.1481
response_variable: answer
```

## Privacy

Only a coordinate is sent, to Google, and only when someone has stopped away from home with
something on a list. Nothing else leaves Home Assistant.
