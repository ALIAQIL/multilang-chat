import os
from django.shortcuts import render, redirect
from chat.models import Room, Message
from django.http import HttpResponse, JsonResponse
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY)

def home(request):
    return render(request, 'home.html')

def room(request, room):
    username = request.GET.get('username')
    language = request.GET.get('language', 'English')  # Default to English
    
    try:
        room_details = Room.objects.get(name=room)
    except Room.DoesNotExist:
        # Create room if it doesn't exist
        room_details = Room.objects.create(name=room)
    
    return render(request, 'room.html', {
        'username': username,
        'room': room,
        'room_details': room_details,
        'language': language
    })

def checkview(request):
    room = request.POST['room_name']
    username = request.POST['username']
    language = request.POST.get('language', 'English')
    
    if not Room.objects.filter(name=room).exists():
        # Create new room if it doesn't exist
        Room.objects.create(name=room)
    
    return redirect(f'/{room}/?username={username}&language={language}')

def send(request):
    message = request.POST['message']
    username = request.POST['username']
    room_id = request.POST['room_id']
    sender_language = request.POST.get('language', 'English')
    
    # Get the room
    room = Room.objects.get(id=room_id)
    
    # First, store the original message in the sender's language
    original_message = Message.objects.create(
        value=message, 
        user=username, 
        room=room_id,
        language=sender_language,
        is_original=True  # Flag as original message
    )
    original_message.save()
    
    # Now get all available languages in this room (from previous messages)
    languages_used = Message.objects.filter(
        room=room_id, 
        is_original=True  # Only look at original messages
    ).values_list('language', flat=True).distinct()
    
    # Include languages from other users in this room
    for target_language in languages_used:
        # Don't translate to the same language
        if target_language.lower() == sender_language.lower():
            continue
            
        try:
            # Translate to this language
            prompt = f"Translate the following message to {target_language}. Return only focus only the translated text without any quotation:\n\n{message} ,"
            
            response = client.chat.completions.create(
                model="mixtral-8x7b-32768",
                messages=[
                    {"role": "system", "content": "You are a translator. Translate exactly what is provided."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=1000,
                temperature=0.3
            )
            
            translated_message = response.choices[0].message.content.strip()
            
            # Create translated message
            translation = Message.objects.create(
                value=translated_message, 
                user=username, 
                room=room_id,
                language=target_language,
                original_id=original_message.id,  # Link to original message
                is_original=False  # Flag as translation
            )
            translation.save()
            
        except Exception as e:
            print(f"Translation error for {target_language}: {str(e)}")
            # Skip this language if translation fails
            continue
    
    return HttpResponse('Message sent successfully')

def getMessages(request, room):
    room_details = Room.objects.get(name=room)
    user_language = request.GET.get('language', 'English')
    
    # Get all message IDs in this room
    all_message_ids = Message.objects.filter(room=room_details.id).values_list('id', flat=True)
    
    # Get all original messages in this room
    original_messages = Message.objects.filter(
        room=room_details.id,
        is_original=True
    )
    
    # Prepare the result list
    result_messages = []
    
    # For each original message
    for orig_msg in original_messages:
        if orig_msg.language.lower() == user_language.lower():
            # If it's already in user's language, use it
            result_messages.append(orig_msg)
        else:
            # Otherwise look for a translation
            translation = Message.objects.filter(
                room=room_details.id,
                original_id=orig_msg.id,
                language=user_language,
                is_original=False
            ).first()
            
            if translation:
                # Use the translation if available
                result_messages.append(translation)
            else:
                # If no translation exists, translate on-the-fly and store for future
                try:
                    prompt = f"Translate the following message to {user_language}. Return only focus only the translated text without any quotation :\n\n{orig_msg.value},"
                    
                    response = client.chat.completions.create(
                        model="mixtral-8x7b-32768",
                        messages=[
                            {"role": "system", "content": "You are a translator."},
                            {"role": "user", "content": prompt},
                        ],
                        max_tokens=1000,
                        temperature=0.3
                    )
                    
                    translated_text = response.choices[0].message.content.strip()
                    
                    # Create and save new translation
                    new_translation = Message.objects.create(
                        value=translated_text,
                        user=orig_msg.user,
                        room=room_details.id,
                        language=user_language,
                        original_id=orig_msg.id,
                        is_original=False,
                        date=orig_msg.date  # Keep original timestamp
                    )
                    new_translation.save()
                    
                    # Add to results
                    result_messages.append(new_translation)
                    
                except Exception as e:
                    print(f"On-the-fly translation error: {str(e)}")
                    # If translation fails, use original message
                    result_messages.append(orig_msg)
    
    # Sort by date
    result_messages.sort(key=lambda x: x.date)
    
    # Convert to list of dictionaries
    messages_list = []
    for msg in result_messages:
        messages_list.append({
            'id': msg.id,
            'value': msg.value,
            'user': msg.user,
            'date': msg.date.strftime("%b %d, %Y, %I:%M %p"),
            'language': msg.language
        })
    
    return JsonResponse({"messages": messages_list})