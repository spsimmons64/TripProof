// People's names are stored the way they are typed - upper case - and shown the way people write
// them. NameCase is the JavaScript port of Perl's Lingua::EN::NameCase, so it knows the cases a
// plain title-case would get wrong: McDonald, O'Brien, MacArthur, van der Berg, de la Cruz,
// hyphenated names and roman-numeral suffixes.
import namecase from 'namecase'

export const properName = (...parts) => namecase(parts.filter(Boolean).join(' ').trim())
